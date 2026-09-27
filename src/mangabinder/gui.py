"""Small desktop window for converting a folder of PDFs to CBZ (mangabinder gui)."""

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, scrolledtext

from mangabinder.cbz import cbz_folder


class RedirectText:
    def __init__(self, q):
        self.q = q

    def write(self, s):
        if s.strip():
            self.q.put(s)

    def flush(self):
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MangaBinder - PDF to CBZ")
        self.geometry("620x420")
        self.resizable(True, True)

        self.folder = tk.StringVar()
        self.log_queue = queue.Queue()

        top = tk.Frame(self, padx=10, pady=10)
        top.pack(fill="x")

        tk.Label(top, text="PDF folder:").pack(side="left")
        tk.Entry(top, textvariable=self.folder).pack(
            side="left", fill="x", expand=True, padx=5)
        tk.Button(top, text="Browse...", command=self.browse).pack(side="left")

        self.run_btn = tk.Button(
            self, text="Convert to CBZ", command=self.run, height=2)
        self.run_btn.pack(fill="x", padx=10, pady=(0, 10))

        self.log = scrolledtext.ScrolledText(self, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.after(100, self.poll_log)

    def browse(self):
        path = filedialog.askdirectory(title="Select folder containing PDFs")
        if path:
            self.folder.set(path)

    def append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text if text.endswith("\n") else text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def poll_log(self):
        try:
            while True:
                self.append_log(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self.poll_log)

    def run(self):
        folder = self.folder.get().strip()
        if not folder:
            self.append_log("[!] Please select a folder first.")
            return
        input_dir = Path(folder)
        if not input_dir.is_dir():
            self.append_log(f"[!] Not a folder: {folder}")
            return
        output_dir = input_dir.with_name(input_dir.name + "_cbz")

        self.run_btn.config(state="disabled", text="Converting...")
        self.append_log(f"[+] Input:  {input_dir}")
        self.append_log(f"[+] Output: {output_dir}")

        threading.Thread(
            target=self.convert_worker,
            args=(input_dir, output_dir),
            daemon=True,
        ).start()

    def convert_worker(self, input_dir, output_dir):
        old_stdout = sys.stdout
        sys.stdout = RedirectText(self.log_queue)
        try:
            cbz_folder(input_dir, output_dir, workers=1, dpi=150, jpeg_quality=85)
        except Exception as e:
            self.log_queue.put(f"[!] Failed: {e}")
        finally:
            sys.stdout = old_stdout
            self.log_queue.put("[OK] Finished.")
            self.after(0, lambda: self.run_btn.config(
                state="normal", text="Convert to CBZ"))


def main():
    App().mainloop()
