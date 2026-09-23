"""Small desktop UI for the live voice-bot assessment prototype.

The call engine remains in app.py; this window only starts/stops it and turns
its existing transcript and nudge messages into a readable call monitor.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk


class VoiceBotUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Native Voice Bot")
        self.root.geometry("940x620")
        self.root.minsize(760, 500)
        self.process: subprocess.Popen[str] | None = None
        self.lines: queue.Queue[str] = queue.Queue()

        root.configure(bg="#f4f7fb")
        header = tk.Frame(root, bg="#102a43", padx=22, pady=16)
        header.pack(fill="x")
        tk.Label(header, text="Native Voice Bot", fg="white", bg="#102a43",
                 font=("Segoe UI", 20, "bold")).pack(side="left")
        tk.Label(header, text="Assessment call monitor", fg="#b9d6ef", bg="#102a43",
                 font=("Segoe UI", 10)).pack(side="left", padx=14, pady=(6, 0))

        controls = tk.Frame(root, bg="#f4f7fb", padx=22, pady=14)
        controls.pack(fill="x")
        tk.Label(controls, text="Market", bg="#f4f7fb", fg="#243b53",
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        self.market = ttk.Combobox(controls, values=("india", "philippines", "indonesia"),
                                    state="readonly", width=16)
        self.market.set("india")
        self.market.pack(side="left", padx=(8, 18))
        self.start_button = ttk.Button(controls, text="Start call", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(controls, text="Stop call", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        self.status = tk.Label(controls, text="Ready", bg="#f4f7fb", fg="#52606d")
        self.status.pack(side="right")

        body = tk.PanedWindow(root, orient="horizontal", sashwidth=6, bg="#d9e2ec")
        body.pack(fill="both", expand=True, padx=22, pady=(0, 18))
        transcript_box = self._panel(body, "Live transcript")
        self.transcript = tk.Text(transcript_box, wrap="word", state="disabled",
                                  bg="white", fg="#243b53", relief="flat", padx=12, pady=10,
                                  font=("Consolas", 10))
        self.transcript.pack(fill="both", expand=True)
        nudge_box = self._panel(body, "Nudges")
        self.nudges = tk.Text(nudge_box, wrap="word", state="disabled",
                              bg="#fffaf0", fg="#7b341e", relief="flat", padx=12, pady=10,
                              font=("Segoe UI", 10))
        self.nudges.pack(fill="both", expand=True)
        body.add(transcript_box, minsize=400)
        body.add(nudge_box, minsize=260)
        self.root.after(100, self.drain_output)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    @staticmethod
    def _panel(parent: tk.PanedWindow, title: str) -> tk.Frame:
        frame = tk.Frame(parent, bg="white", bd=1, relief="solid")
        tk.Label(frame, text=title, anchor="w", bg="white", fg="#102a43",
                 font=("Segoe UI", 11, "bold"), padx=12, pady=9).pack(fill="x")
        return frame

    def _write(self, widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.insert("end", text + "\n")
        widget.see("end")
        widget.configure(state="disabled")

    def start(self) -> None:
        if self.process and self.process.poll() is None:
            return
        env = os.environ.copy()
        python = sys.executable
        self.process = subprocess.Popen(
            [python, "app.py", self.market.get()], stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), env=env,
        )
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.configure(text=f"Live: {self.market.get()}", fg="#147d64")
        threading.Thread(target=self.read_output, daemon=True).start()

    def read_output(self) -> None:
        assert self.process and self.process.stdout
        for line in self.process.stdout:
            self.lines.put(line.rstrip())
        self.lines.put("__PROCESS_DONE__")

    def drain_output(self) -> None:
        try:
            while True:
                line = self.lines.get_nowait()
                if line == "__PROCESS_DONE__":
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.status.configure(text="Call ended", fg="#52606d")
                elif line.startswith("[LIVE NUDGE]") or line.startswith("  ") and "confidence=" in line:
                    self._write(self.nudges, line.strip())
                elif line.startswith("[Customer transcript]") or line.startswith("[Bot transcript]") or line.startswith("[Interrupted"):
                    self._write(self.transcript, line)
        except queue.Empty:
            pass
        self.root.after(100, self.drain_output)

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.status.configure(text="Stopping…", fg="#b44d12")

    def close(self) -> None:
        self.stop()
        self.root.after(150, self.root.destroy)


if __name__ == "__main__":
    root = tk.Tk()
    VoiceBotUI(root)
    root.mainloop()
