"""Simple transcript editor window."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import json


class TranscriptEditor:
    def __init__(self, root, transcript_path=None):
        self.root = root
        self.root.title("Transcript Editor")
        self.root.geometry("900x600")
        self.transcript_path = transcript_path
        self.segments = []
        self._build_ui()
        if transcript_path:
            self.load(transcript_path)

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(btn_frame, text="Open JSON", command=self.open_file).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Save JSON", command=self.save_json).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Export Markdown", command=self.export_markdown).pack(side=tk.LEFT, padx=4)

        self.text = scrolledtext.ScrolledText(frame, wrap=tk.WORD, font=("Consolas", 11))
        self.text.pack(fill=tk.BOTH, expand=True)

    def load(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.segments = data.get("segments", [])
            self._render()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            self.transcript_path = path
            self.load(path)

    def _render(self):
        self.text.delete("1.0", tk.END)
        for seg in self.segments:
            ts = self._fmt(seg.get("start", 0))
            self.text.insert(tk.END, f"[{ts}] {seg.get('text','')}\n")

    def save_json(self):
        if not self.transcript_path:
            path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
            if not path:
                return
            self.transcript_path = path
        # Re-parse edited text back into segments (best-effort: keep original timestamps)
        self._save_text_to_segments()
        data = {"segments": self.segments}
        with open(self.transcript_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("Saved", "Transcript saved.")

    def _save_text_to_segments(self):
        # Keep timestamps from existing segments; update text lines
        lines = self.text.get("1.0", tk.END).strip().splitlines()
        for i, line in enumerate(lines):
            # strip leading [ts]
            if "]" in line:
                text = line.split("]", 1)[-1].strip()
            else:
                text = line.strip()
            if i < len(self.segments):
                self.segments[i]["text"] = text

    def export_markdown(self):
        path = filedialog.asksaveasfilename(defaultextension=".md", filetypes=[("Markdown", "*.md")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            for seg in self.segments:
                ts = self._fmt(seg.get("start", 0))
                f.write(f"[{ts}] {seg.get('text','')}\n")
        messagebox.showinfo("Exported", f"Saved to {path}")

    @staticmethod
    def _fmt(seconds):
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"