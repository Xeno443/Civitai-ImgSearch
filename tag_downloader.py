"""Small window that builds and updates data/tags_all.json from Civitai.

Build DB  (shown while there is no tag file) pages through Civitai's tag
          listing. Fast, about 3,000 requests, but the listing leaves out tags
          that are not PG-rated or not featured.
Update    asks Civitai by id for every id the tag file has no entry for: new
          tags above the highest id, and the gaps below it, which is where the
          hidden tags are. Ids that turn out to be empty are remembered in
          empty_ids.json, so each is asked only once.

Both can be stopped and continued; progress is kept in data/work/.
"""

import ctypes
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk

import civitai
from tagdata import (ALL_TAGS_FILE, WORK_DIR, by_name, load_empty_ids, load_tags, save_empty_ids,
                     save_tags)

PAGES_FILE = WORK_DIR / "build_pages.jsonl"       # Build DB progress, one line per listing page
BATCHES_FILE = WORK_DIR / "update_batches.jsonl"  # Update progress, one line per id batch
END_AFTER_EMPTY = 10       # Update is at the end after this many empty batches above the top id
SECONDS_PER_REQUEST = civitai.REQUEST_DELAY + 0.3  # for time estimates
RETRY_DELAY = 60           # seconds to wait before repeating a failed request
MAX_ATTEMPTS = 10          # failed attempts in a row before a run gives up


def read_progress(path):
    """The records of a progress file. A half-written last line is dropped from the file."""
    records = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            try:
                records.append(json.loads(line))
            except ValueError:
                break
        if len(records) < len(lines):
            path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n"
                                    for record in records), encoding="utf-8")
    return records


def append(output, record):
    output.write(json.dumps(record, ensure_ascii=False) + "\n")
    output.flush()


def duration(requests):
    minutes = round(requests * SECONDS_PER_REQUEST / 60)
    return f"{minutes // 60} h {minutes % 60} min" if minutes >= 60 else f"{max(minutes, 1)} min"


def request(call, argument, report, stop):
    """call(argument), repeated after a pause when it fails, so a long run survives a hiccup.

    The error is raised once MAX_ATTEMPTS have failed in a row, or if Stop is pressed
    during the pause.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return call(argument)
        except Exception as error:
            if attempt == MAX_ATTEMPTS:
                raise
            report(f"Request failed ({error}). Trying again in {RETRY_DELAY} s "
                   f"(attempt {attempt + 1} of {MAX_ATTEMPTS}).")
            if stop.wait(RETRY_DELAY):
                raise


def build_db(report, stop):
    """Page through the listing into the tag file. False if stopped before the end."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    pages = read_progress(PAGES_FILE)
    count = sum(len(page["items"]) for page in pages)
    finished = bool(pages) and len(pages[-1]["items"]) < civitai.PAGE_SIZE
    with PAGES_FILE.open("a", encoding="utf-8") as output:
        while not finished:
            if stop.is_set():
                return False
            number = len(pages) + 1
            items = request(civitai.list_tags, number, report, stop)
            pages.append({"page": number, "items": items})
            append(output, pages[-1])
            count += len(items)
            report(f"Build DB: page {number:,} of about 3,000, {count:,} tags")
            finished = len(items) < civitai.PAGE_SIZE
    tags = {tag_id: name for page in pages for tag_id, name in page["items"]}
    save_tags(ALL_TAGS_FILE, sorted(tags.items(), key=by_name))
    PAGES_FILE.unlink()
    return True


def merge_batches():
    """Move fetched id batches into the tag file and the empty-id record."""
    records = read_progress(BATCHES_FILE)
    if not records:
        return
    tags = dict(load_tags(ALL_TAGS_FILE)[0])
    asked = set()
    for record in records:
        asked.update(record["ids"])
        tags.update((tag_id, name) for tag_id, name in record["tags"])
    # An id above the newest tag is not empty, it just has not been given out yet.
    top = max(tags)
    empty = load_empty_ids() | {tag_id for tag_id in asked if tag_id < top}
    save_tags(ALL_TAGS_FILE, sorted(tags.items(), key=by_name))
    save_empty_ids(empty - tags.keys())
    BATCHES_FILE.unlink()


def unchecked_ids():
    """The ids up to the highest known one with neither a tag nor an empty mark,
    that highest id, and the number of tags on file."""
    known = {tag_id for tag_id, _ in load_tags(ALL_TAGS_FILE)[0]}
    top, count = max(known), len(known)
    known |= load_empty_ids()
    return [tag_id for tag_id in range(1, top + 1) if tag_id not in known], top, count


def update_db(report, stop):
    """Fetch by id what the tag file lacks: new tags first, then the gaps. False if stopped."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    merge_batches()
    gaps, top, _ = unchecked_ids()
    found = 0

    def fetch(output, ids):
        tags = request(civitai.tags_by_id, ids, report, stop)
        append(output, {"ids": ids, "tags": sorted(tags.items())})
        return len(tags)

    try:
        with BATCHES_FILE.open("a", encoding="utf-8") as output:
            empty_run, next_id = 0, top + 1
            while empty_run < END_AFTER_EMPTY and not stop.is_set():
                new = fetch(output, list(range(next_id, next_id + civitai.BATCH_SIZE)))
                empty_run = 0 if new else empty_run + 1
                next_id += civitai.BATCH_SIZE
                found += new
                report(f"Update: new tags, checked up to id {next_id - 1:,}, {found:,} found")
            batches = [gaps[start:start + civitai.BATCH_SIZE]
                       for start in range(0, len(gaps), civitai.BATCH_SIZE)]
            for number, ids in enumerate(batches, 1):
                if stop.is_set():
                    break
                found += fetch(output, ids)
                report(f"Update: gaps, request {number:,} of {len(batches):,}, {found:,} tags "
                       f"found, about {duration(len(batches) - number)} left")
    finally:
        merge_batches()
    return not stop.is_set()


class Downloader:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()  # (kind, *data) from the worker thread
        self.stop = threading.Event()
        self.running = False

        root.title("Civitai Tag Downloader")
        root.geometry("560x230")
        root.minsize(420, 200)
        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)

        self.info = tk.StringVar()
        ttk.Label(frame, textvariable=self.info, wraplength=520, justify="left").pack(anchor="w")
        self.progress = tk.StringVar()
        ttk.Label(frame, textvariable=self.progress, wraplength=520, justify="left").pack(
            anchor="w", pady=(12, 0))

        buttons = ttk.Frame(frame)
        buttons.pack(side="bottom", anchor="w")
        self.action_button = ttk.Button(buttons, command=self.start)
        self.action_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.request_stop)
        self.stop_button.pack(side="left", padx=(6, 0))
        self.stop_button.state(["disabled"])
        self.describe()

    def describe(self):
        """Say what the button will do and what it costs, before anything is requested."""
        if not ALL_TAGS_FILE.exists():
            self.job = build_db
            self.action_button.configure(text="Build DB")
            done = len(read_progress(PAGES_FILE))
            self.info.set(
                "There is no tag file yet. Build DB pages through Civitai's tag listing: about "
                f"3,000 requests, roughly {duration(3000 - done)}"
                + (f" ({done:,} pages are already done)." if done else ".")
                + " It can be stopped and continued.")
            return
        self.job = update_db
        self.action_button.configure(text="Update")
        merge_batches()
        gaps, top, count = unchecked_ids()
        requests = -(-len(gaps) // civitai.BATCH_SIZE)
        self.info.set(
            f"The tag file has {count:,} tags, highest id {top:,}. "
            f"Update asks Civitai for tags newer than that, then for {len(gaps):,} ids below it "
            f"that have not been checked yet: about {requests:,} requests, roughly "
            f"{duration(requests + END_AFTER_EMPTY)}. It can be stopped and continued.")

    def start(self):
        self.running = True
        self.stop.clear()
        self.action_button.state(["disabled"])
        self.stop_button.state(["!disabled"])
        self.progress.set("Starting...")
        threading.Thread(target=self.work, daemon=True).start()
        self.root.after(100, self.poll_events)

    def work(self):
        try:
            finished = self.job(lambda text: self.events.put(("progress", text)), self.stop)
            self.events.put(("done", "Finished." if finished else "Stopped. Progress is kept."))
        except Exception as error:
            if self.stop.is_set():  # Stop pressed while waiting to retry
                self.events.put(("done", "Stopped. Progress is kept."))
            else:
                self.events.put(("done", f"Stopped by an error: {error}. Progress is kept."))

    def request_stop(self):
        self.stop.set()
        self.stop_button.state(["disabled"])
        self.progress.set("Stopping after the current request...")

    def poll_events(self):
        try:
            while True:
                kind, text = self.events.get_nowait()
                if kind == "done":
                    self.running = False
                    self.action_button.state(["!disabled"])
                    self.stop_button.state(["disabled"])
                    self.describe()
                self.progress.set(text)
        except queue.Empty:
            pass
        if self.running:
            self.root.after(100, self.poll_events)


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    Downloader(root)
    root.mainloop()


if __name__ == "__main__":
    main()
