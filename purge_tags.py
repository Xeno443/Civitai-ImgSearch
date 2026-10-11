"""Maintainer step: remove blocked tags from data/tags_all.json.

The block list is sources/blocklist.json, a local file that is never part of
the repo: {"words": [...], "ids": [...], "names": [...]}. A tag is blocked when
its id is listed, its whole name is listed, or any whole word of its name is
listed as a word (a listed "cat" does not match "catgirl"). Without that file
nothing is blocked.

The downloader does not filter, so an Update brings blocked tags back. Run
this again after an Update and before data is published.
build_good_tags.py applies the same block list to the good-tags file.
"""

import json
import re

from tagdata import ALL_TAGS_FILE, SOURCES_DIR, load_tags, save_tags

BLOCKLIST_FILE = SOURCES_DIR / "blocklist.json"


def load_blocklist():
    """The blocked words, ids and names as sets; all empty if there is no block list."""
    try:
        data = json.loads(BLOCKLIST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {key: set(data.get(key, ())) for key in ("words", "ids", "names")}


def is_blocked(tag, blocklist):
    """tag is (id, name). Pass None as the id to test plain text, such as an alias."""
    name = tag[1].lower()
    return (tag[0] in blocklist["ids"] or name in blocklist["names"]
            or not blocklist["words"].isdisjoint(re.findall(r"[^\W_]+", name)))


def main():
    blocklist = load_blocklist()
    tags, fetched_at = load_tags(ALL_TAGS_FILE)
    kept = [tag for tag in tags if not is_blocked(tag, blocklist)]
    if len(kept) < len(tags):
        save_tags(ALL_TAGS_FILE, kept, fetched_at)
    print(f"Removed {len(tags) - len(kept):,} blocked tags from {ALL_TAGS_FILE.name}, "
          f"{len(kept):,} left")


if __name__ == "__main__":
    main()
