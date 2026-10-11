# Civitai Tag Search URL Builder

A small local tool that turns tag names into a Civitai image search URL.

Civitai's image search works on numeric tag IDs, not names:

```
https://civitai.red/images?tags=3647&tags=159160
```

This tool lets you search tags by name, pick the ones you want, and gives you the finished URL. It works from tag files on your disk and does not contact Civitai while you search.

It is an unofficial tool and is not affiliated with Civitai.

## Getting started

### Release zip

The release zip contains everything: the tool, a portable Python, and the full tag list. Unzip it and start `run.bat`. Nothing needs to be installed.

### From a clone of this repository

You need Python 3 with tkinter, which is part of the standard Windows installer from python.org. The tool uses only the standard library, so there are no packages to install. It is developed and tested on Windows with Python 3.13.

Create a virtual environment in the cloned folder and start the scripts from it:

```
python -m venv venv
venv\Scripts\activate
python tag_url_builder.py
```

On Linux or macOS, activate with `source venv/bin/activate` instead.

| Script | What it is |
|---|---|
| `python tag_url_builder.py` | the tag picker |
| `python tag_downloader.py` | the downloader that builds and updates the full tag list |

A clone contains the "good" tag list, which is usually all you need. It does not contain the full tag list; see [Tag data](#tag-data).

## Using the picker

- Type part of a tag name. Matches are listed most-used first.
- Press Enter or double-click a match to add it to the selected tags.
- The search URL at the bottom updates as you add and remove tags. Select it and copy it, or press **Open in browser**.
- Tick **Search everything** to search the full tag list instead of the good one. The box is greyed out if the full list is not there.

Rows in the match list come in three forms:

| Row | Meaning |
|---|---|
| `hands up  [159160]` | a Civitai tag and its ID |
| `spectacles → glasses  [4149]` | "spectacles" is only an alias; selecting the row adds the tag "glasses" |
| `blonde  [508]  (alias of blonde hair)` | a Civitai tag of its own that is also known as an alias of another tag |

## Tag data

| File | Content | Where it comes from |
|---|---|---|
| `data/tags_good.json` | about 56,000 tags that are useful for image search, with popularity counts and aliases | included in this repository |
| `data/tags_all.json` | about 590,000 tags, everything Civitai has | included in the release zip only |

The good list holds the tags whose names are known booru tags or that Civitai files as image tags. The full list adds several hundred thousand tags that users typed on models and posts; most of them are of no use for searching images. **The good list is usually enough.**

If you cloned the repository and want the full list anyway, either copy `data/tags_all.json` and `data/empty_ids.json` out of the release zip, or build the list yourself with the downloader:

1. **Build DB** pages through Civitai's tag listing. About 3,000 requests, roughly 2 hours.
2. **Update** then asks Civitai by ID for everything the listing leaves out. The first run is about 7,800 requests, roughly 5 hours. Later runs only fetch new tags and take minutes.

Both steps can be stopped and continued at any time. The downloader waits 2 seconds between requests and shows the expected number of requests before it starts.

A small number of tags are deliberately left out of the tag files published here. The downloader does not filter, so an Update adds whatever Civitai has.

## Rebuilding the good list

`data/tags_good.json` is made from the full list by `build_good_tags.py`. An Update only adds tags to the full list, so run this afterwards if you want new tags to show up in the normal search.

A tag goes into the good list when its name is in a tag-autocomplete CSV or it is on a trusted list. The CSV also supplies the popularity counts and the aliases.

Put the inputs into a `sources` folder next to the scripts. That folder is ignored by git.

| Input | Needed | What it is |
|---|---|---|
| `data/tags_all.json` | yes | the full tag list |
| `sources/*.csv` | yes | one or more tag-autocomplete CSVs with rows of `name,category,post count,"alias,alias"`, as shipped with the common Danbooru and e621 autocomplete lists |
| `sources/tags_*.json` | no | trusted tag lists in the same format as the full list; every tag in them counts as good |
| `sources/blocklist.json` | no | tags to leave out, as `{"words": [...], "ids": [...], "names": [...]}` |

```
python build_good_tags.py --refresh-image-list
python build_good_tags.py
```

The first command also downloads one trusted list, the tags Civitai files under "Image" (about 90 requests, a few minutes). The second builds from what is already on disk.

`purge_tags.py` removes the tags on the block list from the full list. Without a block list it does nothing.

The published good list was built with a combined Danbooru and e621 CSV, so a rebuild with a different CSV will differ somewhat.

## Good to know

- The tag data comes from an undocumented Civitai endpoint. It can change or stop working without notice.
- Some tags exist but return few or no images, because Civitai has replaced them with another tag.
- The URL points at `civitai.red`. To use a different site, change `SITE` at the top of `tag_url_builder.py`.
