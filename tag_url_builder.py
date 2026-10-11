"""Civitai tag picker: choose image tags by name, get the numeric-ID search URL.

Works from the tag files in data/ and never contacts Civitai itself; see
tag_downloader.py for that.
"""

import ctypes
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from tagdata import (ALL_TAGS_FILE, GOOD_TAGS_FILE, build_entries, label, load_good, load_tags,
                     match_entries)

SITE = "https://civitai.red"  # site the built search URL points at
MAX_RESULTS = 200


def build_url(tags):
    if not tags:
        return ""
    return f"{SITE}/images?" + "&".join(f"tags={tag_id}" for tag_id, _ in tags)


class App:
    def __init__(self, root, good_tags, counts, alias_of):
        self.root = root
        self.good_tags, self.counts, self.alias_of = good_tags, counts, alias_of
        self.entries = build_entries(good_tags, counts, alias_of)
        self.all_entries = None  # built the first time "Search everything" is used
        self.results = []   # entries currently listed as matches
        self.selected = []  # tags that go into the URL

        root.title("Civitai Tag URL Builder")
        root.geometry("760x520")
        root.minsize(560, 360)

        frame = ttk.Frame(root, padding=10)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1, uniform="lists")
        frame.columnconfigure(1, weight=1, uniform="lists")
        frame.rowconfigure(2, weight=1)

        ttk.Label(frame, text="Search tag").grid(row=0, column=0, sticky="w")
        self.search_all = tk.BooleanVar()
        search_all_box = ttk.Checkbutton(frame, text="Search everything", variable=self.search_all,
                                         command=self.update_results)
        search_all_box.grid(row=0, column=0, sticky="e", padx=(0, 5))
        if not ALL_TAGS_FILE.exists():
            search_all_box.state(["disabled"])
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *_: self.update_results())
        self.search = ttk.Entry(frame, textvariable=self.query)
        self.search.grid(row=1, column=0, sticky="ew", padx=(0, 5), pady=(2, 6))
        self.search.bind("<Return>", lambda _: self.add_result(clear_query=True))
        self.search.bind("<Down>", lambda _: self.move_selection(1))
        self.search.bind("<Up>", lambda _: self.move_selection(-1))

        ttk.Label(frame, text="Selected tags").grid(row=0, column=1, sticky="w", padx=(5, 0))
        buttons = ttk.Frame(frame)
        buttons.grid(row=1, column=1, sticky="w", padx=(5, 0), pady=(2, 6))
        ttk.Button(buttons, text="Remove", command=self.remove_selected).pack(side="left")
        ttk.Button(buttons, text="Clear", command=self.clear_selected).pack(side="left", padx=(6, 0))

        self.result_list = self._listbox(frame, column=0, padx=(0, 5))
        self.result_list.bind("<Double-Button-1>", lambda _: self.add_result())
        self.result_list.bind("<Return>", lambda _: self.add_result())

        self.selected_list = self._listbox(frame, column=1, padx=(5, 0))
        self.selected_list.bind("<Double-Button-1>", lambda _: self.remove_selected())
        self.selected_list.bind("<Delete>", lambda _: self.remove_selected())

        ttk.Label(frame, text="Search URL").grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.url = tk.StringVar()
        url_row = ttk.Frame(frame)
        url_row.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(2, 8))
        url_row.columnconfigure(0, weight=1)
        ttk.Entry(url_row, textvariable=self.url, state="readonly").grid(
            row=0, column=0, sticky="ew")
        self.open_button = ttk.Button(
            url_row, text="Open in browser", command=lambda: webbrowser.open(self.url.get()))
        self.open_button.grid(row=0, column=1, padx=(6, 0))
        self.open_button.state(["disabled"])

        self.status = tk.StringVar()
        ttk.Label(frame, textvariable=self.status).grid(
            row=5, column=0, columnspan=2, sticky="ew")

        self.update_results()
        self.search.focus_set()

    def _listbox(self, parent, column, padx):
        box = ttk.Frame(parent)
        box.grid(row=2, column=column, sticky="nsew", padx=padx)
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)
        listbox = tk.Listbox(box, exportselection=False, activestyle="none")
        scrollbar = ttk.Scrollbar(box, command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        return listbox

    def active_entries(self):
        if not self.search_all.get():
            return self.entries
        if self.all_entries is None:
            self.status.set("Loading all tags...")
            self.root.update_idletasks()
            all_tags = set(load_tags(ALL_TAGS_FILE)[0]) | set(self.good_tags)
            self.all_count = len(all_tags)
            self.all_entries = build_entries(all_tags, self.counts, self.alias_of)
        return self.all_entries

    def update_results(self):
        found = match_entries(self.active_entries(), self.query.get())
        self.results = found[:MAX_RESULTS]
        if not self.query.get().strip():
            count = self.all_count if self.search_all.get() else len(self.good_tags)
            self.status.set(f"{count:,} tags")
        elif len(found) > MAX_RESULTS:
            self.status.set(
                f"Showing {MAX_RESULTS} of {len(found):,} matches - type more to narrow.")
        else:
            self.status.set(f"{len(found):,} {'match' if len(found) == 1 else 'matches'}")
        self.result_list.delete(0, "end")
        self.result_list.insert("end", *(entry[1] for entry in self.results))
        if self.results:
            self.result_list.selection_set(0)

    def move_selection(self, step):
        if self.results:
            current = self.result_list.curselection()
            index = (current[0] + step) if current else 0
            index = max(0, min(len(self.results) - 1, index))
            self.result_list.selection_clear(0, "end")
            self.result_list.selection_set(index)
            self.result_list.see(index)
        return "break"

    def add_result(self, clear_query=False):
        current = self.result_list.curselection()
        if not current:
            return
        tag = self.results[current[0]][2]
        if tag not in self.selected:
            self.selected.append(tag)
            self.show_selected()
        if clear_query:
            self.query.set("")

    def remove_selected(self):
        current = self.selected_list.curselection()
        if not current:
            return
        del self.selected[current[0]]
        self.show_selected()
        if self.selected:
            self.selected_list.selection_set(min(current[0], len(self.selected) - 1))

    def clear_selected(self):
        self.selected.clear()
        self.show_selected()

    def show_selected(self):
        self.selected_list.delete(0, "end")
        self.selected_list.insert("end", *map(label, self.selected))
        self.url.set(build_url(self.selected))
        self.open_button.state(["!disabled" if self.selected else "disabled"])


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    good_tags, counts, alias_of = load_good()
    if not good_tags:
        root.withdraw()
        messagebox.showerror(
            "Civitai Tag URL Builder",
            f"The tag file {GOOD_TAGS_FILE.name} is missing from the data folder or cannot be "
            "read.\n\nGet it from the project's release, or build it with build_good_tags.py.")
        return
    App(root, good_tags, counts, alias_of)
    root.mainloop()


if __name__ == "__main__":
    main()
