"""Meeting transcription engine (Whisper-based, supports EN/BM)."""

import os
import json
import time
import threading
from datetime import datetime, timedelta


class MeetingTranscriber:
    def __init__(self, model_size="base", language="auto", progress_callback=None):
        self.model_size = model_size
        self.language = language  # 'en', 'ms', or 'auto'
        self.progress_callback = progress_callback
        self.model = None
        self.backend = None
        self.stop_event = None
        self._load_model()

    def _log(self, msg):
        if self.progress_callback:
            try:
                self.progress_callback({"type": "log", "message": msg})
            except Exception:
                pass

    def _progress(self, pct, msg):
        if self.progress_callback:
            try:
                self.progress_callback({"type": "progress", "percent": pct, "message": msg})
            except Exception:
                pass

    def _load_model(self):
        self._log(f"Loading Whisper model '{self.model_size}'...")
        try:
            from faster_whisper import WhisperModel
            self.backend = "faster"
            self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        except Exception:
            try:
                import whisper
                self.backend = "openai"
                self.model = whisper.load_model(self.model_size)
            except Exception as e:
                raise RuntimeError(
                    "No Whisper backend found. Install faster-whisper or openai-whisper.\n" + str(e)
                )
        self._log("Model loaded.")

    def _audio_duration(self, path):
        try:
            import av
            container = av.open(path)
            if container.duration is not None:
                return container.duration / 1_000_000.0
            # fallback: last frame
            stream = container.streams.audio[0]
            if stream.duration is not None:
                return float(stream.duration * stream.time_base)
        except Exception:
            pass
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(path)
            return len(audio) / 1000.0
        except Exception:
            return 0.0

    def transcribe_meeting(self, audio_path, meeting_name, chunk_length_min=5,
                           meeting_date=None, start_time=None, participants=None,
                           stop_event=None):
        """Transcribe an audio file and return a structured result dict."""
        self.stop_event = stop_event
        if meeting_date is None:
            meeting_date = datetime.now().strftime("%Y-%m-%d")
        if start_time is None:
            start_time = datetime.now().strftime("%H:%M")

        self._log(f"Transcribing: {os.path.basename(audio_path)}")

        duration = self._audio_duration(audio_path)
        self._log(f"Audio duration: {round(duration/60, 1)} min")

        lang = None if self.language == "auto" else self.language

        segments = []
        detected_lang = self.language
        cancelled = False
        t0 = time.time()

        if self.backend == "faster":
            segs, info = self.model.transcribe(audio_path, language=lang, beam_size=5)
            detected_lang = info.language
            for s in segs:
                if stop_event is not None and stop_event.is_set():
                    cancelled = True
                    break
                segments.append({
                    "start": round(s.start, 2),
                    "end": round(s.end, 2),
                    "text": s.text.strip(),
                })
                if duration > 0:
                    pct = min(99, int((s.end / duration) * 100))
                    elapsed = time.time() - t0
                    if s.end > 0 and elapsed > 0:
                        speed = s.end / elapsed
                        remaining = max(0, (duration - s.end) / speed)
                        eta = time.strftime("%M:%S", time.gmtime(remaining))
                    else:
                        eta = "--:--"
                    self._progress(pct, f"Transcribing... {pct}% (ETA {eta})")
        else:
            self._progress(10, "Transcribing (openai-whisper)...")
            result = self.model.transcribe(audio_path, language=lang)
            for s in result.get("segments", []):
                if stop_event is not None and stop_event.is_set():
                    cancelled = True
                    break
                segments.append({
                    "start": round(s["start"], 2),
                    "end": round(s["end"], 2),
                    "text": s["text"].strip(),
                })
            detected_lang = result.get("language", self.language)
            self._progress(95, "Finalizing...")

        if cancelled:
            self._log("Transcription cancelled by user.")
            raise RuntimeError("Cancelled by user")

        self._progress(100, "Done")

        duration_sec = segments[-1]["end"] if segments else 0
        try:
            start_dt = datetime.strptime(f"{meeting_date} {start_time}", "%Y-%m-%d %H:%M")
            end_dt = start_dt + timedelta(seconds=duration_sec)
            end_time = end_dt.strftime("%H:%M")
        except Exception:
            end_time = start_time

        result = {
            "meeting_name": meeting_name,
            "meeting_date": meeting_date,
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": duration_sec,
            "detected_language": detected_lang,
            "participants": participants or [],
            "chunks_created": 1,
            "segments": segments,
            "output_folder": os.path.dirname(os.path.abspath(audio_path)),
        }

        # Save JSON
        out_json = os.path.join(result["output_folder"], f"{meeting_name}_transcript.json")
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        self._log(f"Saved transcript: {out_json}")

        # Save Markdown minutes
        out_md = os.path.join(result["output_folder"], f"{meeting_name}_minutes.md")
        with open(out_md, "w", encoding="utf-8") as f:
            f.write(self.to_markdown(result))
        self._log(f"Saved minutes: {out_md}")

        return result

    @staticmethod
    def to_markdown(result):
        lines = []
        lines.append(f"# MEETING MINUTES — {result['meeting_name'].upper()}")
        lines.append("")
        lines.append("## Meeting Details")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|---|---|")
        lines.append(f"| **Date** | {result['meeting_date']} |")
        lines.append(f"| **Start Time** | {result['start_time']} |")
        lines.append(f"| **End Time** | {result['end_time']} |")
        lines.append(f"| **Duration** | {round(result['duration_seconds']/60, 1)} minutes |")
        lines.append(f"| **Language** | {result['detected_language']} |")
        if result.get("participants"):
            lines.append(f"| **Participants** | {', '.join(result['participants'])} |")
        lines.append("")
        lines.append("## Agenda")
        lines.append("")
        lines.append("1. _(Add agenda items here)_")
        lines.append("")
        lines.append("## Discussion / Perbincangan")
        lines.append("")
        for seg in result["segments"]:
            ts = MeetingTranscriber._fmt_ts(seg["start"])
            lines.append(f"[{ts}] {seg['text']}")
        lines.append("")
        lines.append("## Decisions / Keputusan")
        lines.append("")
        lines.append("- _(Record decisions here)_")
        lines.append("")
        lines.append("## Action Items / Tindakan")
        lines.append("")
        lines.append("| # | Action | Owner | Due Date | Status |")
        lines.append("|---|---|---|---|---|")
        lines.append("| 1 | _(action)_ | _(owner)_ | _(date)_ | Pending |")
        lines.append("")
        lines.append("## Next Meeting")
        lines.append("")
        lines.append("_(Date/time of next meeting)_")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def export_docx(result, path):
        try:
            from docx import Document
        except Exception:
            raise RuntimeError("python-docx not installed. Run: pip install python-docx")
        doc = Document()
        doc.add_heading(f"Meeting Minutes — {result['meeting_name']}", 0)
        table = doc.add_table(rows=0, cols=2)
        table.style = 'Table Grid'
        for k, v in [
            ("Date", result['meeting_date']),
            ("Start Time", result['start_time']),
            ("End Time", result['end_time']),
            ("Duration", f"{round(result['duration_seconds']/60,1)} min"),
            ("Language", result['detected_language']),
            ("Participants", ", ".join(result.get('participants', []))),
        ]:
            row = table.add_row().cells
            row[0].text = k
            row[1].text = str(v)
        doc.add_heading("Transcript", level=1)
        for seg in result["segments"]:
            p = doc.add_paragraph()
            p.add_run(f"[{MeetingTranscriber._fmt_ts(seg['start'])}] ").bold = True
            p.add_run(seg["text"])
        doc.add_heading("Minutes / Action Items", level=1)
        doc.add_paragraph("Decisions and action items to be filled in.")
        doc.save(path)

    @staticmethod
    def export_pdf(result, path):
        try:
            from fpdf import FPDF
        except Exception:
            raise RuntimeError("fpdf2 not installed. Run: pip install fpdf2")
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, f"Meeting Minutes - {result['meeting_name']}", ln=True)
        pdf.set_font("Helvetica", size=11)
        for k, v in [
            ("Date", result['meeting_date']),
            ("Start", result['start_time']),
            ("End", result['end_time']),
            ("Duration", f"{round(result['duration_seconds']/60,1)} min"),
            ("Language", result['detected_language']),
        ]:
            pdf.cell(0, 8, f"{k}: {v}", ln=True)
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Transcript", ln=True)
        pdf.set_font("Helvetica", size=10)
        for seg in result["segments"]:
            pdf.multi_cell(0, 6, f"[{MeetingTranscriber._fmt_ts(seg['start'])}] {seg['text']}")
        pdf.output(path)

    @staticmethod
    def _fmt_ts(seconds):
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def set_progress_callback(self, cb):
        self.progress_callback = cb