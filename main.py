# main.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import threading
import webbrowser
import logging
import traceback
from tkcalendar import DateEntry

# Configure file logging
_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "meeting_transcriber.log")
logging.basicConfig(
    filename=_LOG_FILE,
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
from datetime import datetime
from meeting_transcriber import MeetingTranscriber
from version_check import APP_VERSION, RELEASES_PAGE, check_for_update, is_newer

class MeetingTranscriberApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Meeting Transcriber v{APP_VERSION}")
        self.root.geometry("800x600")
        self.transcriber = None
        self.current_audio_file = ""
        self.latest_version = None
        self.latest_url = None
        
        self.setup_ui()
    
    def setup_ui(self):
        """Create the user interface"""
        # Apply a modern ttk theme
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure('TButton', padding=6, font=('Segoe UI', 10))
        style.configure('TLabel', font=('Segoe UI', 10))
        style.configure('TLabelframe.Label', font=('Segoe UI', 10, 'bold'))
        style.configure('Title.TLabel', font=('Segoe UI', 16, 'bold'), foreground='#2b3a67')

        # Main frame
        main_frame = ttk.Frame(self.root, padding="16")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="Meeting Audio Transcriber", 
                               style='Title.TLabel')
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Audio file selection
        ttk.Label(main_frame, text="Meeting Audio File:").grid(row=1, column=0, sticky=tk.W, pady=5)
        
        self.file_path_var = tk.StringVar()
        self.file_entry = ttk.Entry(main_frame, textvariable=self.file_path_var, width=50)
        self.file_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5, padx=(5, 5))
        
        self.browse_btn = ttk.Button(main_frame, text="📂 Browse", command=self.browse_audio_file)
        self.browse_btn.grid(row=1, column=2, pady=5)
        
        # Meeting info
        ttk.Label(main_frame, text="Meeting Name:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.meeting_name_var = tk.StringVar()
        self.meeting_name_entry = ttk.Entry(main_frame, textvariable=self.meeting_name_var, width=50)
        self.meeting_name_entry.grid(row=2, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        ttk.Label(main_frame, text="Meeting Date:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.meeting_date_entry = DateEntry(main_frame, width=20, date_pattern='yyyy-mm-dd')
        self.meeting_date_entry.grid(row=3, column=1, sticky=tk.W, pady=5)

        ttk.Label(main_frame, text="Start Time:").grid(row=4, column=0, sticky=tk.W, pady=5)
        time_frame = ttk.Frame(main_frame)
        time_frame.grid(row=4, column=1, sticky=tk.W, pady=5)
        self.start_hour_var = tk.StringVar(value=datetime.now().strftime("%H"))
        self.start_minute_var = tk.StringVar(value=datetime.now().strftime("%M"))
        ttk.Spinbox(time_frame, from_=0, to=23, width=4, textvariable=self.start_hour_var, format="%02.0f").pack(side=tk.LEFT)
        ttk.Label(time_frame, text=":").pack(side=tk.LEFT)
        ttk.Spinbox(time_frame, from_=0, to=59, width=4, textvariable=self.start_minute_var, format="%02.0f").pack(side=tk.LEFT)

        ttk.Label(main_frame, text="Participants:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.participants_var = tk.StringVar()
        self.participants_entry = ttk.Entry(main_frame, textvariable=self.participants_var, width=50)
        self.participants_entry.grid(row=5, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        # Settings frame
        settings_frame = ttk.LabelFrame(main_frame, text="Transcription Settings", padding="10")
        settings_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        settings_frame.columnconfigure(1, weight=1)
        
        # Model selection
        ttk.Label(settings_frame, text="Model Size:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.model_var = tk.StringVar(value="base")
        model_combo = ttk.Combobox(settings_frame, textvariable=self.model_var, 
                                  values=["tiny", "base", "small", "medium", "large"], 
                                  state="readonly", width=15)
        model_combo.grid(row=0, column=1, sticky=tk.W, pady=2)
        ttk.Label(settings_frame, text="Larger = more accurate but slower (tiny/base/small/medium/large)", foreground='gray', font=('Arial', 8)).grid(row=0, column=2, sticky=tk.W, pady=2)
        
        # Chunk size
        ttk.Label(settings_frame, text="Chunk Size (minutes):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.chunk_size_var = tk.StringVar(value="5")
        chunk_spin = ttk.Spinbox(settings_frame, from_=1, to=30, textvariable=self.chunk_size_var, width=15)
        chunk_spin.grid(row=1, column=1, sticky=tk.W, pady=2)

        # Language
        ttk.Label(settings_frame, text="Language:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.lang_var = tk.StringVar(value="auto")
        lang_combo = ttk.Combobox(settings_frame, textvariable=self.lang_var,
                                  values=["auto", "en", "ms"], state="readonly", width=15)
        lang_combo.grid(row=2, column=1, sticky=tk.W, pady=2)
        
        # Progress section
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="10")
        progress_frame.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        progress_frame.columnconfigure(0, weight=1)
        
        self.progress_var = tk.StringVar(value="Ready")
        self.progress_label = ttk.Label(progress_frame, textvariable=self.progress_var)
        self.progress_label.grid(row=0, column=0, sticky=tk.W)
        
        self.progress = ttk.Progressbar(progress_frame, mode='determinate', maximum=100)
        self.progress.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        
        self.stop_btn = ttk.Button(progress_frame, text="⏹ Stop", command=self.stop_transcription, state="disabled")
        self.stop_btn.grid(row=1, column=1, padx=(8,0), pady=5)
        
        # Log output
        ttk.Label(main_frame, text="Processing Log:").grid(row=8, column=0, sticky=tk.W, pady=(10, 0))
        self.log_text = scrolledtext.ScrolledText(main_frame, height=15, width=80)
        self.log_text.grid(row=9, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=10, column=0, columnspan=3, pady=10)
        
        self.transcribe_btn = ttk.Button(button_frame, text="▶ Start", command=self.start_transcription)
        self.transcribe_btn.pack(side=tk.LEFT, padx=5)
        
        self.open_editor_btn = ttk.Button(button_frame, text="📝 Editor", command=self.open_editor, state="disabled")
        self.open_editor_btn.pack(side=tk.LEFT, padx=5)
        
        self.clear_log_btn = ttk.Button(button_frame, text="🧹 Clear Log", command=self.clear_log)
        self.clear_log_btn.pack(side=tk.LEFT, padx=5)
        
        self.about_btn = ttk.Button(button_frame, text="ℹ️ About", command=self.show_about)
        self.about_btn.pack(side=tk.LEFT, padx=5)

        self.copy_log_btn = ttk.Button(button_frame, text="📋 Copy Log", command=self.copy_log)
        self.copy_log_btn.pack(side=tk.LEFT, padx=5)

        self.check_update_btn = ttk.Button(button_frame, text="🔄 Check Update", command=self.check_update)
        self.check_update_btn.pack(side=tk.LEFT, padx=5)

        self.export_docx_btn = ttk.Button(button_frame, text="📄 Word", command=self.export_docx, state="disabled")
        self.export_docx_btn.pack(side=tk.LEFT, padx=5)
        self.export_pdf_btn = ttk.Button(button_frame, text="📑 PDF", command=self.export_pdf, state="disabled")
        self.export_pdf_btn.pack(side=tk.LEFT, padx=5)
        
        # Configure row weights for proper resizing
        main_frame.rowconfigure(9, weight=1)
    
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
        """Add message to log"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def clear_log(self):
        """Clear the log text"""
        self.log_text.delete(1.0, tk.END)
    
    def start_transcription(self):
        """Start the transcription process in a separate thread"""
        if not self.file_path_var.get():
            messagebox.showerror("Error", "Please select an audio file")
            return
        
        if not self.meeting_name_var.get():
            messagebox.showerror("Error", "Please enter a meeting name")
            return
        
        # Disable buttons during processing
        self.transcribe_btn.config(state="disabled")
        self.browse_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress.config(value=0)
        self.stop_event = threading.Event()
        
        # Start transcription in separate thread
        thread = threading.Thread(target=self.run_transcription)
        thread.daemon = True
        thread.start()
    
    def run_transcription(self):
        """Run the transcription process"""
        try:
            self.log_message("Initializing transcriber...")
            
            # Initialize transcriber
            self.transcriber = MeetingTranscriber(model_size=self.model_var.get(), language=self.lang_var.get())
            
            # Set progress callback
            self.transcriber.set_progress_callback(self.update_progress)
            
            # Start transcription
            audio_file = self.file_path_var.get()
            meeting_name = self.meeting_name_var.get() or os.path.splitext(os.path.basename(audio_file))[0]
            chunk_size = int(self.chunk_size_var.get())
            meeting_date = self.meeting_date_entry.get()
            start_time = f"{int(self.start_hour_var.get()):02d}:{int(self.start_minute_var.get()):02d}"
            participants = [p.strip() for p in self.participants_var.get().split(",") if p.strip()]
            
            self.log_message(f"Starting transcription for: {meeting_name}")
            self.log_message(f"Audio file: {os.path.basename(audio_file)}")
            self.log_message(f"Chunk size: {chunk_size} minutes")
            self.log_message(f"Language: {self.lang_var.get()}")
            self.log_message("-" * 50)
            
            result = self.transcriber.transcribe_meeting(
                audio_path=audio_file,
                meeting_name=meeting_name,
                chunk_length_min=chunk_size,
                meeting_date=meeting_date,
                start_time=start_time,
                participants=participants,
                stop_event=self.stop_event
            )
            
            self.log_message("-" * 50)
            self.log_message("Transcription completed successfully!")
            self.log_message(f"Chunks created: {result['chunks_created']}")
            self.log_message(f"Start: {result['start_time']}  End: {result['end_time']}  Duration: {round(result['duration_seconds']/60,1)} min")
            self.log_message(f"Detected language: {result['detected_language']}")
            self.log_message(f"Output folder: {result['output_folder']}")
            
            # Enable editor button
            self.open_editor_btn.config(state="normal")
            self.export_docx_btn.config(state="normal")
            self.export_pdf_btn.config(state="normal")
            self.last_result = result
            self.last_transcript_path = os.path.join(result['output_folder'], f"{meeting_name}_transcript.json")
            
            messagebox.showinfo("Success", "Transcription completed successfully!")
            
        except Exception as e:
            tb = traceback.format_exc()
            error_msg = f"Error during transcription: {str(e)}"
            self.log_message(error_msg)
            self.log_message(tb)
            logging.exception("Transcription failed")
            messagebox.showerror("Error", error_msg + "\n\nFull details saved to:\n" + _LOG_FILE)
        finally:
            # Re-enable buttons
            self.transcribe_btn.config(state="normal")
            self.browse_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.progress_var.set("Ready")
    
    def update_progress(self, payload):
        """Update progress from transcriber"""
        if isinstance(payload, dict):
            if payload.get("type") == "log":
                self.log_message(payload.get("message", ""))
                return
            if payload.get("type") == "progress":
                pct = payload.get("percent", 0)
                msg = payload.get("message", "")
                try:
                    self.progress.config(value=pct)
                except Exception:
                    pass
                self.progress_var.set(f"{msg}")
                self.log_message(msg)
                return
        # fallback: string
        msg = str(payload)
        self.progress_var.set(msg)
        self.log_message(msg)
    
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
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(defaultextension=".docx", filetypes=[("Word", "*.docx")])
        if not path:
            return
        try:
            MeetingTranscriber.export_docx(self.last_result, path)
            messagebox.showinfo("Saved", f"Saved to {path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def export_pdf(self):
        if not getattr(self, "last_result", None):
            messagebox.showwarning("No data", "Transcribe first.")
            return
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        try:
            MeetingTranscriber.export_pdf(self.last_result, path)
            messagebox.showinfo("Saved", f"Saved to {path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def copy_log(self):
        try:
            content = self.log_text.get("1.0", tk.END)
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            messagebox.showinfo("Copied", "Log copied to clipboard.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def export_docx(self):
        if not getattr(self, "last_result", None):
            messagebox.showwarning("No data", "Transcribe first.")
            return
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(defaultextension=".docx", filetypes=[("Word", "*.docx")])
        if not path:
            return
        try:
            MeetingTranscriber.export_docx(self.last_result, path)
            messagebox.showinfo("Saved", f"Saved to {path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def export_pdf(self):
        if not getattr(self, "last_result", None):
            messagebox.showwarning("No data", "Transcribe first.")
            return
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        try:
            MeetingTranscriber.export_pdf(self.last_result, path)
            messagebox.showinfo("Saved", f"Saved to {path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def copy_log(self):
        try:
            content = self.log_text.get("1.0", tk.END)
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            messagebox.showinfo("Copied", "Log copied to clipboard.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def stop_transcription(self):
        if getattr(self, "stop_event", None):
            self.stop_event.set()
            self.log_message("Stop requested...")

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
        about.geometry("460x300")
        ttk.Label(about, text=f"Meeting Transcriber v{APP_VERSION}", font=("Arial", 14, "bold")).pack(pady=(15,5))
        ttk.Label(about, text="Transcribe meetings with timestamps (EN/BM).").pack()
        ttk.Label(about, text="Developer: Rashid Zainol - JANN Sarawak").pack(pady=5)
        link = ttk.Label(about, text="GitHub: rashidzainol/MeetingTranscipt", foreground="blue", cursor="hand2")
        link.pack(pady=5)
        link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/rashidzainol/MeetingTranscipt"))
        latest_text = self.latest_version if self.latest_version else "Not checked yet"
        ttk.Label(about, text=f"Latest version: {latest_text}").pack(pady=5)
        ttk.Button(about, text="Check Update", command=self.check_update).pack(pady=4)
        ttk.Button(about, text="Close", command=about.destroy).pack(pady=10)

if __name__ == "__main__":
    root = tk.Tk()
    app = MeetingTranscriberApp(root)
    root.mainloop()