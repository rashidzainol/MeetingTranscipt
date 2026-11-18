# main.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sys
import time
import platform
import threading
import webbrowser
import logging
import traceback
from tkcalendar import DateEntry


def _app_data_dir():
    """Persistent folder for the log file.

    Kept outside the application folder so that updates, read-only install
    locations and PyInstaller's temporary extraction folder never lose the log.
    """
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".meeting_transcriber")
        try:
            os.makedirs(base, exist_ok=True)
        except Exception:
            pass
        return base
    base = os.path.join(base, "MeetingTranscriber")
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass
    return base


APP_DIR = _app_data_dir()
_LOG_FILE = os.path.join(APP_DIR, "meeting_transcriber.log")


def _setup_logging():
    """Write an INFO-level rotating log file (2 MB x 3 files).

    Third-party libraries are silenced so the log only contains the
    information a user or developer needs when reporting a problem.
    """
    from logging.handlers import RotatingFileHandler

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Remove handlers installed by an earlier import (e.g. the update checker).
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    try:
        handler = RotatingFileHandler(
            _LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        root.addHandler(handler)
    except Exception:
        # A read-only folder must never stop the app from starting.
        root.addHandler(logging.NullHandler())

    for name in (
        "urllib3",
        "httpx",
        "httpcore",
        "huggingface_hub",
        "PIL",
        "faster_whisper",
        "ctranslate2",
        "numba",
        "matplotlib",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)


_setup_logging()
from datetime import datetime
from meeting_transcriber import MeetingTranscriber
from version_check import (
    APP_VERSION,
    APP_UPDATED,
    APP_COPYRIGHT,
    RELEASES_PAGE,
    check_for_update,
    is_newer,
)

class MeetingTranscriberApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Meeting Transcriber v{APP_VERSION}")
        self.transcriber = None
        self.current_audio_file = ""
        self.latest_version = None
        self.latest_url = None
        self.last_result = None
        self.stop_event = None
        self.running = False

        self.setup_ui()
        self._apply_geometry()
        self._log_startup_info()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _apply_geometry(self):
        """Size and centre the window, but never larger than the screen."""
        self.root.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        req_w, req_h = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        w = min(max(1000, req_w), sw - 60)
        h = min(max(720, req_h), sh - 100)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(min(880, sw - 40), min(680, sh - 80))

    def _log_startup_info(self):
        self.log_message("=" * 64)
        self.log_message(f"Meeting Transcriber v{APP_VERSION}  (updated {APP_UPDATED})")
        self.log_message(f"Started: {datetime.now():%Y-%m-%d %H:%M:%S}")
        self.log_message(
            f"Python {sys.version.split()[0]}  |  Frozen EXE: "
            f"{'yes' if getattr(sys, 'frozen', False) else 'no'}"
        )
        self.log_message(f"Platform: {platform.platform()}")
        self.log_message(f"CPU: {os.cpu_count()} logical cores")
        try:
            import psutil
            self.log_message(f"RAM: {psutil.virtual_memory().total / (1024 ** 3):.1f} GB")
        except Exception:
            pass
        self.log_message(f"Log file: {_LOG_FILE}")
        self.log_message("Tip: Whisper speed depends on CPU cores, model size, RAM and GPU — see README → Performance.")
        self.log_message("=" * 64)
        logging.info("Startup information written to log.")
    
    def setup_ui(self):
        """Create the user interface."""
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure('TButton', padding=(10, 6), font=('Segoe UI', 10))
        style.configure('TLabel', font=('Segoe UI', 10))
        style.configure('TLabelframe.Label', font=('Segoe UI', 10, 'bold'))
        style.configure('Title.TLabel', font=('Segoe UI', 17, 'bold'), foreground='#2b3a67')
        style.configure('Sub.TLabel', font=('Segoe UI', 9), foreground='#6b7280')
        style.configure('Hint.TLabel', font=('Segoe UI', 8), foreground='#6b7280')
        style.configure('Status.TLabel', font=('Segoe UI', 10, 'bold'))

        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        # ---------- Header ----------
        header = ttk.Frame(main)
        header.pack(fill=tk.X)
        ttk.Label(header, text="Meeting Audio Transcriber", style='Title.TLabel').pack(side=tk.LEFT)
        ttk.Label(
            header,
            text=f"v{APP_VERSION}  ·  updated {APP_UPDATED}",
            style='Sub.TLabel',
        ).pack(side=tk.RIGHT, anchor=tk.S)

        # ---------- Meeting details ----------
        details = ttk.LabelFrame(main, text="Meeting Details", padding=8)
        details.pack(fill=tk.X, pady=(8, 6))
        details.columnconfigure(1, weight=1)

        ttk.Label(details, text="Audio file").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=3)
        self.file_path_var = tk.StringVar()
        self.file_entry = ttk.Entry(details, textvariable=self.file_path_var)
        self.file_entry.grid(row=0, column=1, sticky=tk.EW, pady=3)
        self.browse_btn = ttk.Button(details, text="📂 Browse", command=self.browse_audio_file)
        self.browse_btn.grid(row=0, column=2, padx=(8, 0), pady=3)

        ttk.Label(details, text="Meeting name").grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=3)
        self.meeting_name_var = tk.StringVar()
        self.meeting_name_entry = ttk.Entry(details, textvariable=self.meeting_name_var)
        self.meeting_name_entry.grid(row=1, column=1, columnspan=2, sticky=tk.EW, pady=3)

        ttk.Label(details, text="Date / start").grid(row=2, column=0, sticky=tk.W, padx=(0, 8), pady=3)
        when = ttk.Frame(details)
        when.grid(row=2, column=1, columnspan=2, sticky=tk.W, pady=3)
        self.meeting_date_entry = DateEntry(when, width=12, date_pattern='yyyy-mm-dd')
        self.meeting_date_entry.pack(side=tk.LEFT)
        ttk.Label(when, text="  at  ").pack(side=tk.LEFT)
        self.start_hour_var = tk.StringVar(value=datetime.now().strftime("%H"))
        self.start_minute_var = tk.StringVar(value=datetime.now().strftime("%M"))
        ttk.Spinbox(when, from_=0, to=23, width=4, textvariable=self.start_hour_var, format="%02.0f").pack(side=tk.LEFT)
        ttk.Label(when, text=":").pack(side=tk.LEFT)
        ttk.Spinbox(when, from_=0, to=59, width=4, textvariable=self.start_minute_var, format="%02.0f").pack(side=tk.LEFT)
        ttk.Label(
            when, text="  end time follows the audio length",
            style='Hint.TLabel',
        ).pack(side=tk.LEFT, padx=(10, 0))

        ttk.Label(details, text="Participants").grid(row=3, column=0, sticky=tk.W, padx=(0, 8), pady=3)
        self.participants_var = tk.StringVar()
        self.participants_entry = ttk.Entry(details, textvariable=self.participants_var)
        self.participants_entry.grid(row=3, column=1, columnspan=2, sticky=tk.EW, pady=3)

        # ---------- Settings ----------
        settings = ttk.LabelFrame(main, text="Transcription Settings", padding=8)
        settings.pack(fill=tk.X)
        settings.columnconfigure(3, weight=1)

        ttk.Label(settings, text="Model size").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=3)
        self.model_var = tk.StringVar(value="base")
        ttk.Combobox(
            settings, textvariable=self.model_var,
            values=["tiny", "base", "small", "medium", "large"],
            state="readonly", width=12,
        ).grid(row=0, column=1, sticky=tk.W, pady=3)

        ttk.Label(settings, text="Language").grid(row=0, column=2, sticky=tk.W, padx=(18, 8), pady=3)
        self.lang_var = tk.StringVar(value="auto")
        ttk.Combobox(
            settings, textvariable=self.lang_var,
            values=["auto", "en", "ms"], state="readonly", width=10,
        ).grid(row=0, column=3, sticky=tk.W, pady=3)

        ttk.Label(
            settings,
            text=("tiny/base = fastest · small = balanced · medium/large = more accurate but slow. "
                  "Language: auto = detect, en = English, ms = Bahasa Malaysia."),
            style='Hint.TLabel',
            wraplength=820,
        ).grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=(4, 0))

        # ---------- Progress ----------
        progress = ttk.LabelFrame(main, text="Progress", padding=8)
        progress.pack(fill=tk.X, pady=6)
        progress.columnconfigure(0, weight=1)

        self.progress_var = tk.StringVar(value="Ready")
        self.progress_detail_var = tk.StringVar(value="Idle — choose an audio file, then press Start.")
        ttk.Label(progress, textvariable=self.progress_var, style='Status.TLabel').grid(
            row=0, column=0, sticky=tk.W)
        self.progress = ttk.Progressbar(progress, mode='determinate', maximum=100)
        self.progress.grid(row=1, column=0, sticky=tk.EW, pady=(4, 2))
        ttk.Label(progress, textvariable=self.progress_detail_var, style='Hint.TLabel').grid(
            row=2, column=0, sticky=tk.W)

        self.stop_btn = ttk.Button(
            progress, text="⏹ Stop", command=self.stop_transcription, state="disabled")
        self.stop_btn.grid(row=0, column=1, rowspan=3, padx=(10, 0), sticky=tk.NS)

        # ---------- Action bar (packed before the log so it is always visible) ----------
        actions = ttk.Frame(main)
        actions.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        self.actions_bar = actions
        ttk.Separator(actions, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 6))

        primary = ttk.Frame(actions)
        primary.pack(fill=tk.X)
        self.transcribe_btn = ttk.Button(primary, text="▶ Start", command=self.start_transcription)
        self.transcribe_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.open_editor_btn = ttk.Button(
            primary, text="📝 Editor", command=self.open_editor, state="disabled")
        self.open_editor_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.export_docx_btn = ttk.Button(
            primary, text="📄 Word", command=self.export_docx, state="disabled")
        self.export_docx_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.export_pdf_btn = ttk.Button(
            primary, text="📑 PDF", command=self.export_pdf, state="disabled")
        self.export_pdf_btn.pack(side=tk.LEFT, padx=(0, 6))

        secondary = ttk.Frame(actions)
        secondary.pack(fill=tk.X, pady=(5, 0))
        self.clear_log_btn = ttk.Button(secondary, text="🧹 Clear Log", command=self.clear_log)
        self.clear_log_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.copy_log_btn = ttk.Button(secondary, text="📋 Copy Log", command=self.copy_log)
        self.copy_log_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.open_log_btn = ttk.Button(secondary, text="📂 Log Folder", command=self.open_log_folder)
        self.open_log_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.check_update_btn = ttk.Button(secondary, text="🔄 Check Update", command=self.check_update)
        self.check_update_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.about_btn = ttk.Button(secondary, text="ℹ️ About", command=self.show_about)
        self.about_btn.pack(side=tk.RIGHT)

        # ---------- Processing log (visible by default, grows with the window) ----------
        log_frame = ttk.LabelFrame(main, text="Processing Log", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_frame = log_frame
        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=6, width=80, wrap=tk.WORD, font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Keyboard shortcuts
        self.root.bind("<Control-o>", lambda e: self.browse_audio_file())
        self.root.bind("<Control-O>", lambda e: self.browse_audio_file())
        self.root.bind("<F5>", lambda e: self.start_transcription())
        self.root.bind("<Escape>", lambda e: self.stop_transcription())
    
    def browse_audio_file(self):
        """Browse for audio file"""
        file_types = [
            ("Audio files", "*.mp3 *.wav *.m4a *.aac *.flac"),
            ("MP3 files", "*.mp3"),
            ("WAV files", "*.wav"),
            ("M4A files", "*.m4a"),
            ("All files", "*.*")
        ]
        
        filename = filedialog.askopenfilename(title="Select Meeting Audio File", filetypes=file_types)
        if filename:
            self.file_path_var.set(filename)
            # Auto-fill meeting name from filename
            meeting_name = os.path.splitext(os.path.basename(filename))[0]
            self.meeting_name_var.set(meeting_name)
    
    def log_message(self, message):
        """Append one line to the on-screen log and the log file."""
        if threading.current_thread() is not threading.main_thread():
            try:
                self.root.after(0, self.log_message, message)
            except Exception:
                pass
            return
        line = f"[{datetime.now():%H:%M:%S}] {message}"
        self.log_text.insert(tk.END, line + "\n")
        self.log_text.see(tk.END)
        logging.info(message)
    
    def clear_log(self):
        """Clear the log text"""
        self.log_text.delete(1.0, tk.END)
    
    def start_transcription(self):
        """Start the transcription process in a separate thread"""
        if self.running:
            return
        if not self.file_path_var.get():
            messagebox.showerror("Error", "Please select an audio file")
            return

        if not self.meeting_name_var.get():
            messagebox.showerror("Error", "Please enter a meeting name")
            return

        # Disable buttons during processing
        self.transcribe_btn.config(state="disabled")
        self.browse_btn.config(state="disabled")
        self.open_editor_btn.config(state="disabled")
        self.export_docx_btn.config(state="disabled")
        self.export_pdf_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress.config(value=0)
        self.progress_var.set("Starting...")
        self.progress_detail_var.set("Preparing the transcription engine.")
        self.stop_event = threading.Event()
        self.running = True

        # Start transcription in separate thread
        thread = threading.Thread(target=self.run_transcription, daemon=True)
        thread.start()

    def run_transcription(self):
        """Run the heavy transcription work off the UI thread."""
        t0 = time.time()
        try:
            audio_file = self.file_path_var.get()
            meeting_name = self.meeting_name_var.get() or os.path.splitext(
                os.path.basename(audio_file))[0]
            model_size = self.model_var.get()
            language = self.lang_var.get()
            meeting_date = self.meeting_date_entry.get()
            start_time = f"{int(self.start_hour_var.get()):02d}:{int(self.start_minute_var.get()):02d}"
            participants = [p.strip() for p in self.participants_var.get().split(",") if p.strip()]

            try:
                size_mb = os.path.getsize(audio_file) / (1024 * 1024)
            except Exception:
                size_mb = 0.0

            self.log_message("-" * 64)
            self.log_message(f"Preparing transcription: {meeting_name}")
            self.log_message(f"Audio: {os.path.basename(audio_file)} ({size_mb:.1f} MB)")
            self.log_message(
                f"Model: {model_size} | Language: {language} | "
                f"Participants: {len(participants)}"
            )
            self.update_progress({
                "type": "progress",
                "percent": 1,
                "message": "Loading model...",
                "detail": "First run downloads the model (internet required once).",
            })

            self.transcriber = MeetingTranscriber(
                model_size=model_size,
                language=language,
                progress_callback=self.update_progress,
            )
            self.log_message(f"Transcriber ready after {time.time() - t0:.1f}s.")

            result = self.transcriber.transcribe_meeting(
                audio_path=audio_file,
                meeting_name=meeting_name,
                chunk_length_min=5,
                meeting_date=meeting_date,
                start_time=start_time,
                participants=participants,
                stop_event=self.stop_event,
            )
        except Exception as e:
            tb = traceback.format_exc()
            self.log_message(f"Error during transcription: {e}")
            self.log_message(tb)
            logging.exception("Transcription failed")
            if "Cancelled by user" in str(e):
                self.root.after(0, self._finish_cancelled)
            else:
                self.root.after(0, lambda: self._finish_error(e, tb))
            return

        self.root.after(0, lambda: self._finish_success(result, time.time() - t0))

    def _finish_success(self, result, wall_seconds):
        self.running = False
        self.log_message("-" * 64)
        self.log_message(
            f"Transcription completed successfully in "
            f"{MeetingTranscriber._fmt_dur(wall_seconds)}."
        )
        self.log_message(
            f"Audio length: {MeetingTranscriber._fmt_dur(result['duration_seconds'])} | "
            f"{result['start_time']} → {result['end_time']}"
        )
        self.log_message(
            f"Language: {result['detected_language']} | Segments: {len(result['segments'])}"
        )
        self.log_message(f"Output folder: {result['output_folder']}")

        self.last_result = result
        self.last_transcript_path = os.path.join(
            result['output_folder'], f"{result['meeting_name']}_transcript.json")

        self.transcribe_btn.config(state="normal")
        self.browse_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.open_editor_btn.config(state="normal")
        self.export_docx_btn.config(state="normal")
        self.export_pdf_btn.config(state="normal")
        self.progress.config(value=100)
        self.progress_var.set("Completed")
        self.progress_detail_var.set(
            f"{len(result['segments'])} segments · total {MeetingTranscriber._fmt_dur(wall_seconds)}"
        )
        messagebox.showinfo(
            "Success",
            "Transcription completed.\n\n"
            f"Saved next to the audio file:\n{result['output_folder']}",
        )

    def _finish_cancelled(self):
        self.running = False
        self.transcribe_btn.config(state="normal")
        self.browse_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.progress_var.set("Stopped")
        self.progress_detail_var.set("Stopped by user — no files were saved.")
        if self.last_result is not None:
            self.open_editor_btn.config(state="normal")
            self.export_docx_btn.config(state="normal")
            self.export_pdf_btn.config(state="normal")
        messagebox.showinfo("Stopped", "Transcription stopped. No files were saved.")

    def _finish_error(self, exc, tb):
        self.running = False
        self.transcribe_btn.config(state="normal")
        self.browse_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.progress_var.set("Failed")
        self.progress_detail_var.set("See the log for details, then use Copy Log to share it.")
        messagebox.showerror(
            "Error",
            f"Error during transcription: {exc}\n\n"
            f"Full details saved to:\n{_LOG_FILE}\n\n"
            "Use 'Copy Log' if you need to share the error.",
        )
    
    def update_progress(self, payload):
        """Thread-safe progress callback used by the transcriber."""
        try:
            self.root.after(0, self._apply_progress, payload)
        except Exception:
            pass

    def _apply_progress(self, payload):
        if isinstance(payload, dict):
            kind = payload.get("type")
            if kind == "log":
                self.log_message(payload.get("message", ""))
                return
            if kind == "progress":
                pct = payload.get("percent", 0)
                try:
                    self.progress.config(value=pct)
                except Exception:
                    pass
                self.progress_var.set(payload.get("message", ""))
                detail = payload.get("detail", "")
                if detail:
                    self.progress_detail_var.set(detail)
                return
        # fallback: plain string
        self.progress_var.set(str(payload))
    
    def open_editor(self):
        """Open the transcript editor"""
        try:
            from transcript_editor import TranscriptEditor
            editor_window = tk.Toplevel(self.root)
            path = getattr(self, "last_transcript_path", None)
            editor_app = TranscriptEditor(editor_window, transcript_path=path)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot open editor: {str(e)}")

    def export_docx(self):
        if not getattr(self, "last_result", None):
            messagebox.showwarning("No data", "Transcribe first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".docx",
            initialfile=self._default_export_name(".docx"),
            filetypes=[("Word document", "*.docx")],
        )
        if not path:
            return
        try:
            MeetingTranscriber.export_docx(self.last_result, path)
            self.log_message(f"Word minutes saved: {path}")
            messagebox.showinfo("Saved", f"Saved to:\n{path}")
        except Exception as e:
            self._report_export_error("Word", e)

    def export_pdf(self):
        if not getattr(self, "last_result", None):
            messagebox.showwarning("No data", "Transcribe first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=self._default_export_name(".pdf"),
            filetypes=[("PDF document", "*.pdf")],
        )
        if not path:
            return
        try:
            MeetingTranscriber.export_pdf(self.last_result, path)
            self.log_message(f"PDF minutes saved: {path}")
            messagebox.showinfo("Saved", f"Saved to:\n{path}")
        except Exception as e:
            self._report_export_error("PDF", e)

    def _default_export_name(self, ext):
        name = "meeting"
        try:
            name = self.last_result.get("meeting_name") or name
        except Exception:
            pass
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip()
        return f"{safe or 'meeting'}_minutes{ext}"

    def _report_export_error(self, kind, exc):
        tb = traceback.format_exc()
        self.log_message(f"{kind} export failed: {exc}")
        self.log_message(tb)
        logging.exception("%s export failed", kind)
        messagebox.showerror(
            "Export failed",
            f"Could not create the {kind} file:\n{exc}\n\n"
            f"Details were written to the log:\n{_LOG_FILE}\n\n"
            "Use 'Copy Log' if you need to share the error.",
        )

    def copy_log(self):
        try:
            content = self.log_text.get("1.0", tk.END)
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            messagebox.showinfo("Copied", "Log copied to clipboard.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def open_log_folder(self):
        try:
            os.startfile(os.path.dirname(_LOG_FILE))
        except Exception:
            messagebox.showinfo("Log folder", os.path.dirname(_LOG_FILE))

    def stop_transcription(self):
        if self.stop_event is not None and not self.stop_event.is_set():
            self.stop_event.set()
            self.log_message("Stop requested — finishing the current segment...")
            self.progress_var.set("Stopping...")
            self.progress_detail_var.set("Waiting for the current segment to finish.")
            self.stop_btn.config(state="disabled")

    def on_close(self):
        if self.running and self.stop_event is not None:
            if not messagebox.askyesno(
                "Quit",
                "A transcription is still running.\nStop it and quit?",
            ):
                return
            self.stop_event.set()
        logging.info("Application closed.")
        self.root.destroy()

    def check_update(self):
        self.check_update_btn.config(state="disabled")
        self.log_message("Checking for updates...")
        threading.Thread(target=self._check_update_thread, daemon=True).start()

    def _check_update_thread(self):
        latest, url, notes = check_for_update()
        self.root.after(0, lambda: self._update_done(latest, url, notes))

    def _update_done(self, latest, url, notes):
        self.check_update_btn.config(state="normal")
        if not latest:
            self.log_message("Update check failed (offline?)")
            return
        self.latest_version = latest
        self.latest_url = url
        if is_newer(latest, APP_VERSION):
            msg = f"New version {latest} available! (Current: v{APP_VERSION})"
            self.log_message(msg)
            if messagebox.askyesno("Update Available", msg + "\n\nOpen download page?"):
                webbrowser.open(url or RELEASES_PAGE)
        else:
            self.log_message(f"You are up to date (v{APP_VERSION}).")
            messagebox.showinfo("Up to date", f"Current version: v{APP_VERSION}\nLatest: {latest}\nNo update needed.")

    def show_about(self):
        about = tk.Toplevel(self.root)
        about.title("About Meeting Transcriber")
        about.geometry("520x430")
        about.resizable(False, False)
        about.transient(self.root)

        ttk.Label(about, text="Meeting Transcriber", font=("Segoe UI", 16, "bold")).pack(pady=(18, 2))
        ttk.Label(
            about,
            text=f"Version {APP_VERSION}  ·  updated {APP_UPDATED}",
            style='Sub.TLabel',
        ).pack()
        ttk.Label(
            about,
            text="Transcribe meetings with timestamps (English / Bahasa Malaysia).",
        ).pack(pady=(10, 2))
        ttk.Label(about, text="Developer: Rashid Zainol — JANN Sarawak").pack()
        ttk.Label(about, text=APP_COPYRIGHT, style='Sub.TLabel').pack(pady=(2, 8))

        link = ttk.Label(
            about,
            text="github.com/rashidzainol/MeetingTranscipt",
            foreground="blue",
            cursor="hand2",
        )
        link.pack()
        link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/rashidzainol/MeetingTranscipt"))

        ttk.Separator(about).pack(fill=tk.X, padx=20, pady=10)

        latest_text = self.latest_version if self.latest_version else "Not checked yet"
        ttk.Label(about, text=f"Latest version on GitHub: {latest_text}").pack()
        ttk.Label(
            about,
            text=f"Running on: {platform.system()} {platform.release()} · {os.cpu_count()} CPU cores",
            style='Sub.TLabel',
        ).pack(pady=(4, 0))
        ttk.Label(
            about,
            text=f"Engine: Whisper (faster-whisper) · Logs: {os.path.dirname(_LOG_FILE)}",
            style='Sub.TLabel',
        ).pack(pady=(2, 8))

        buttons = ttk.Frame(about)
        buttons.pack(pady=6)
        ttk.Button(buttons, text="🔄 Check Update", command=self.check_update).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Close", command=about.destroy).pack(side=tk.LEFT, padx=4)

if __name__ == "__main__":
    # Make text crisp on high-DPI Windows displays.
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    try:
        from ctypes import windll
        root.tk.call("tk", "scaling", windll.user32.GetDpiForSystem() / 72.0)
    except Exception:
        pass
    app = MeetingTranscriberApp(root)
    root.mainloop()