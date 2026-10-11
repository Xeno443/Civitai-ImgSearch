"""Tag files and tag search, shared by the picker, the downloader and the build step."""

import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
WORK_DIR = DATA_DIR / "work"    # download progress; safe to delete while nothing is running
SOURCES_DIR = ROOT / "sources"  # originals the good-tags file is built from; never shipped

GOOD_TAGS_FILE = DATA_DIR / "tags_good.json"  # tags searched by default, see build_good_tags.py
ALL_TAGS_FILE = DATA_DIR / "tags_all.json"    # every tag fetched from Civitai, see tag_downloader.py
EMPTY_IDS_FILE = DATA_DIR / "empty_ids.json"  # ids Civitai has no tag for, so Update asks only once

# How a typed query is compared against the (lowercased) text of an entry.
MATCHERS = {
    "prefix": lambda query, text: text.startswith(query),
    "contains": lambda query, text: query in text,
}
MATCH_MODE = "prefix"


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = path.with_suffix(".tmp")
    temp_file.write_text(text, encoding="utf-8")
    os.replace(temp_file, path)


def _rows(rows):
    """A JSON array body with one row per line, so the file stays readable in an editor."""
    return ",\n".join(json.dumps(row, ensure_ascii=False) for row in rows)


def by_name(tag):
    return tag[1].lower()


def load_tags(path):
    """A tag file as ((id, name) pairs, time it was fetched); empty if it cannot be read."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [(tag_id, name) for tag_id, name in data["tags"]], data["fetched_at"]
    except (OSError, ValueError, KeyError, TypeError):
        return [], None


def save_tags(path, tags, fetched_at=None):
    if fetched_at is None:
        fetched_at = time.time()
    _write(path, f'{{"fetched_at": {json.dumps(fetched_at)}, "tags": [\n{_rows(tags)}\n]}}\n')


def load_good():
    """The good tags, post counts by tag name, and alias -> name of the tag it stands for."""
    try:
        data = json.loads(GOOD_TAGS_FILE.read_text(encoding="utf-8"))
        names = {tag_id: name for tag_id, name, _ in data["tags"]}
        counts = {name.lower(): count for _, name, count in data["tags"]}
        alias_of = {alias: names[tag_id].lower() for alias, tag_id in data["aliases"]}
        return list(names.items()), counts, alias_of
    except (OSError, ValueError, KeyError, TypeError):
        return [], {}, {}


def save_good(tags, aliases):
    """tags are (id, name, post count) rows, aliases are (alias, id of the tag it stands for)."""
    _write(GOOD_TAGS_FILE, f'{{"built_at": {json.dumps(time.time())}, "tags": [\n{_rows(tags)}\n],'
                           f' "aliases": [\n{_rows(aliases)}\n]}}\n')


def load_empty_ids():
    try:
        data = json.loads(EMPTY_IDS_FILE.read_text(encoding="utf-8"))
        return {tag_id for first, last in data["ranges"] for tag_id in range(first, last + 1)}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def save_empty_ids(ids, path=None):
    """Stored as [first, last] runs of consecutive ids, which is far shorter than one per id."""
    ranges = []
    for tag_id in sorted(ids):
        if ranges and tag_id == ranges[-1][1] + 1:
            ranges[-1][1] = tag_id
        else:
            ranges.append([tag_id, tag_id])
    _write(path or EMPTY_IDS_FILE, f'{{"ranges": [\n{_rows(ranges)}\n]}}\n')


def booru_name(text):
    """A booru tag name the way Civitai writes it: spaces, lowercase."""
    return text.strip().replace("_", " ").lower()


def label(tag):
    return f"{tag[1]}  [{tag[0]}]"


def build_entries(tags, counts, alias_of):
    """Search entries for the given tags: real tag names first, then alias rows,
    each group most-used first.

    An entry is (text to match, text to show, tag it selects). A tag whose name
    is a booru alias keeps its own entry with a note; an alias without a tag of
    its own becomes an extra entry that selects the tag it stands for.
    """
    named = {by_name(tag): tag for tag in tags}
    ranked = []
    for name, tag in named.items():
        target = alias_of.get(name)
        note = f"  (alias of {target})" if target in named else ""
        ranked.append((0, -counts.get(name, 0), name.replace("_", " "), label(tag) + note, tag))
    for alias, target in alias_of.items():
        if alias not in named and target in named:
            tag = named[target]
            ranked.append((1, -counts.get(target, 0), alias, f"{alias} → {label(tag)}", tag))
    ranked.sort()
    return [(text, shown, tag) for _, _, text, shown, tag in ranked]


def match_entries(entries, query, mode=MATCH_MODE):
    """Every entry matching the query, best-ranked first, at most one per tag."""
    query = booru_name(query)
    if not query:
        return []
    matcher = MATCHERS[mode]
    found, seen = [], set()
    for entry in entries:
        if matcher(query, entry[0]) and entry[2][0] not in seen:
            seen.add(entry[2][0])
            found.append(entry)
    return found
