"""Maintainer step: build data/tags_good.json, the tags the picker searches by default.

A tag is good when its name is a booru tag name (from the CSV files in
sources/) or it is on a trusted list (sources/tags_*.json), and it is not on
the block list (see purge_tags.py). Post counts and aliases are copied in from
the CSV, so the picker needs neither the CSV nor the lists.

    python build_good_tags.py                        build from what is on disk
    python build_good_tags.py --refresh-image-list   first re-download Civitai's
                                                     Image-category tag list (~90 requests)
"""

import csv
import sys

import civitai
from purge_tags import is_blocked, load_blocklist
from tagdata import (ALL_TAGS_FILE, GOOD_TAGS_FILE, SOURCES_DIR, booru_name, by_name, load_tags,
                     save_good, save_tags)

IMAGE_LIST_FILE = SOURCES_DIR / "tags_image.json"  # the tags Civitai files under "Image"


def refresh_image_list():
    tags = {}
    for page in range(1, 500):
        items = civitai.list_tags(page, entity_type="Image")
        tags.update(items)
        print(f"image list: page {page}, {len(tags):,} tags", flush=True)
        if len(items) < civitai.PAGE_SIZE:
            break
    save_tags(IMAGE_LIST_FILE, sorted(tags.items(), key=by_name))


def load_csv():
    """Post counts by tag name and alias -> tag name, from the CSV files in sources/.

    CSV rows are name,category,post count,"alias,alias,..." with booru-style names.
    """
    counts, alias_of = {}, {}
    for path in sorted(SOURCES_DIR.glob("*.csv")):
        with open(path, encoding="utf-8", newline="") as handle:
            for row in csv.reader(handle):
                if not row or booru_name(row[0]) in counts:
                    continue
                name = booru_name(row[0])
                counts[name] = int(row[2]) if len(row) > 2 and row[2].isdigit() else 0
                if len(row) > 3:
                    for alias in row[3].split(","):
                        if booru_name(alias):
                            alias_of.setdefault(booru_name(alias), name)
    # A name that is a tag in its own right is not treated as an alias.
    return counts, {alias: name for alias, name in alias_of.items() if alias not in counts}


def main():
    if "--refresh-image-list" in sys.argv:
        refresh_image_list()
    all_tags, _ = load_tags(ALL_TAGS_FILE)
    if not all_tags:
        sys.exit(f"{ALL_TAGS_FILE.name} is missing - build it with the downloader first")
    counts, alias_of = load_csv()

    names = {}  # id -> name of every good tag
    for path in sorted(SOURCES_DIR.glob("tags_*.json")):
        names.update(load_tags(path)[0])
    # The full list has the current name, so it wins over a trusted list's copy.
    names.update(tag for tag in all_tags if by_name(tag) in counts or tag[0] in names)
    blocklist = load_blocklist()
    names = {tag_id: name for tag_id, name in names.items()
             if not is_blocked((tag_id, name), blocklist)}

    tags = sorted(((tag_id, name, counts.get(name.lower(), 0)) for tag_id, name in names.items()),
                  key=lambda tag: (-tag[2], tag[1].lower()))
    ids = {name.lower(): tag_id for tag_id, name in names.items()}
    # An alias is only text, so it is checked against the block list without an id.
    aliases = sorted(((alias, ids[target]) for alias, target in alias_of.items()
                      if target in ids and not is_blocked((None, alias), blocklist)),
                     key=lambda alias: (-counts[alias_of[alias[0]]], alias[0]))
    save_good(tags, aliases)
    print(f"Wrote {len(tags):,} tags and {len(aliases):,} aliases to {GOOD_TAGS_FILE.name}")


if __name__ == "__main__":
    main()
