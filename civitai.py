"""Requests to Civitai's tag endpoints. Every request goes through here, paced."""

import json
import time
import urllib.parse
import urllib.request

API_HOST = "https://civitai.com"
PAGE_SIZE = 200       # tags per listing page; the endpoint rejects anything larger
BATCH_SIZE = 30       # ids per by-id request; the endpoint rejects 50
REQUEST_DELAY = 2.0   # seconds between requests, so Civitai is never hammered

# The endpoint answers 401 unless the request looks like it came from the site.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/129.0 Safari/537.36",
    "Referer": f"{API_HOST}/images",
    "Accept": "application/json",
}

_last_request = 0.0


def _get(path):
    """Fetch /api/trpc/<path> as JSON, waiting out the delay since the last request."""
    global _last_request
    wait = _last_request + REQUEST_DELAY - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    request = urllib.request.Request(f"{API_HOST}/api/trpc/{path}", headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    finally:
        _last_request = time.monotonic()


def _input(payload):
    return urllib.parse.quote(json.dumps(payload, separators=(",", ":")))


def list_tags(page, entity_type=None):
    """One page of Civitai's tag listing, in name order, as (id, name) pairs.

    The listing only has PG-rated, featured tags; the rest are reachable by id.
    """
    params = {"limit": PAGE_SIZE, "page": page}
    if entity_type:
        params["entityType"] = [entity_type]
    answer = _get("tag.getAll?input=" + _input({"json": params}))
    return [(item["id"], item["name"]) for item in answer["result"]["data"]["json"]["items"]]


def tags_by_id(ids):
    """The tags that exist among up to BATCH_SIZE ids, as id -> name.

    Unlike the listing this also returns hidden tags. Ids without a tag are
    simply missing from the result.
    """
    calls = ",".join(["tag.getById"] * len(ids))
    payload = {str(number): {"json": {"id": tag_id}} for number, tag_id in enumerate(ids)}
    tags = {}
    for answer in _get(f"{calls}?batch=1&input=" + _input(payload)):
        if "error" in answer:
            raise RuntimeError(answer["error"]["json"]["message"])
        tag = answer["result"]["data"]["json"]
        if tag:
            tags[tag["id"]] = tag["name"]
    return tags
