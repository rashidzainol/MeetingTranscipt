"""Meeting transcription engine (Whisper-based, supports EN/BM)."""

import os
import json
import time
import threading
from datetime import datetime, timedelta

try:
    from version_check import APP_VERSION
except Exception:  # pragma: no cover - version module is optional at import time
    APP_VERSION = "1.10.0"


class MeetingTranscriber:
    def __init__(self, model_size="base", language="auto", progress_callback=None,
                 device="auto"):
        self.model_size = model_size
        self.language = language  # 'en', 'ms', or 'auto'
        self.progress_callback = progress_callback
        self.model = None
        self.backend = None
        self.stop_event = None
        self.device_requested = device
        self.device = "cpu"
        self.compute_type = "int8"
        self._load_model()

    def _log(self, msg):
        if self.progress_callback:
            try:
                self.progress_callback({"type": "log", "message": msg})
            except Exception:
                pass

    def _progress(self, pct, msg, detail=""):
        if self.progress_callback:
            try:
                self.progress_callback({
                    "type": "progress",
                    "percent": pct,
                    "message": msg,
                    "detail": detail,
                })
            except Exception:
                pass

    def _load_model(self):
        t0 = time.time()
        self._progress(2, f"Loading model '{self.model_size}'...",
                       detail="The first run downloads the model (internet required once).")
        self._log(f"Loading Whisper model '{self.model_size}' (requested device: {self.device_requested})...")

        # faster-whisper can use an NVIDIA GPU (CUDA) which is far faster than CPU.
        if self.device_requested == "auto":
            try:
                import ctranslate2
                if ctranslate2.get_cuda_device_count() > 0:
                    self.device, self.compute_type = "cuda", "float16"
            except Exception:
                pass
        else:
            self.device = self.device_requested
            self.compute_type = "float16" if self.device == "cuda" else "int8"

        WhisperModel = None
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            self._log(f"faster-whisper not available ({exc}).")

        if WhisperModel is not None:
            self.backend = "faster"
            try:
                self.model = WhisperModel(
                    self.model_size, device=self.device, compute_type=self.compute_type
                )
            except Exception as first_exc:
                if self.device != "cpu":
                    self._log(
                        f"GPU could not be used ({first_exc}). Falling back to CPU (int8)."
                    )
                    self.device, self.compute_type = "cpu", "int8"
                    self.model = WhisperModel(
                        self.model_size, device="cpu", compute_type="int8"
                    )
                else:
                    raise
        else:
            self._log("Falling back to openai-whisper (slower on CPU)...")
            try:
                import whisper
                self.backend = "openai"
                self.device, self.compute_type = "cpu", "float32"
                self.model = whisper.load_model(self.model_size)
            except Exception as e:
                raise RuntimeError(
                    "No Whisper backend found. Install faster-whisper or openai-whisper.\n" + str(e)
                )

        elapsed = time.time() - t0
        if self.backend == "faster":
            self._log(
                f"Backend ready: faster-whisper | device={self.device.upper()} | "
                f"compute={self.compute_type} | model load={elapsed:.1f}s"
            )
            if self.device == "cpu":
                self._log(
                    "Running on CPU. An NVIDIA GPU with CUDA can be several times faster — "
                    "see README → Performance."
                )
        else:
            self._log(
                f"Backend ready: openai-whisper | device=CPU | model load={elapsed:.1f}s"
            )
            self._log("Note: faster-whisper is usually 3-4x faster than openai-whisper on CPU.")
        self._progress(
            6, "Model ready",
            detail=f"{self.backend} · {self.device.upper()} · {self.compute_type} · {elapsed:.1f}s",
        )


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

        t_start = time.time()
        try:
            file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        except Exception:
            file_size_mb = 0.0

        self._log("-" * 62)
        self._log(f"Job: {meeting_name}")
        self._log(f"File: {os.path.basename(audio_path)} ({file_size_mb:.1f} MB)")
        self._log(
            f"Model: {self.model_size} | Backend: {self.backend} | "
            f"Device: {self.device.upper()} | Compute: {self.compute_type}"
        )
        self._log(f"Language: {self.language} | Participants: {len(participants or [])}")
        try:
            import shutil
            free_gb = shutil.disk_usage(
                os.path.dirname(os.path.abspath(audio_path))
            ).free / (1024 ** 3)
            self._log(f"Free disk space in output folder: {free_gb:.1f} GB")
        except Exception:
            pass

        self._progress(8, "Reading audio...", detail="Checking duration and stream information.")
        duration = self._audio_duration(audio_path)
        if duration > 0:
            self._log(f"Audio duration: {self._fmt_dur(duration)} ({duration / 60:.1f} min)")
        else:
            self._log("Audio duration: unknown (progress bar uses the last processed timestamp)")
        try:
            import av
            with av.open(audio_path) as container:
                stream = container.streams.audio[0]
                self._log(
                    f"Audio stream: {stream.codec_context.name} · {stream.rate} Hz · "
                    f"{stream.channels} channel(s)"
                )
        except Exception:
            self._log("Audio stream details: unavailable")

        lang = None if self.language == "auto" else self.language

        segments = []
        detected_lang = self.language
        cancelled = False
        t0 = time.time()
        # Log less often on short audio and more often on very long recordings.
        step = 0.05 if duration > 3600 else 0.10
        next_log = step

        self._log("Transcription started — this is the CPU/GPU intensive stage.")
        if self.backend == "faster":
            self._progress(10, "Transcribing...", detail="Whisper is analysing the audio now.")
            segs, info = self.model.transcribe(audio_path, language=lang, beam_size=5)
            detected_lang = info.language
            prob = getattr(info, "language_probability", 0) or 0
            self._log(f"Detected language: {detected_lang} (probability {prob:.2f})")
            for s in segs:
                if stop_event is not None and stop_event.is_set():
                    cancelled = True
                    break
                segments.append({
                    "start": round(s.start, 2),
                    "end": round(s.end, 2),
                    "text": s.text.strip(),
                })
                elapsed = time.time() - t0
                if duration > 0:
                    frac = min(1.0, s.end / duration)
                    pct = min(99, int(frac * 100))
                    speed = s.end / elapsed if elapsed > 0 else 0
                    remaining = max(0.0, (duration - s.end) / speed) if speed > 0 else 0
                    self._progress(
                        10 + int(pct * 0.85),
                        f"Transcribing... {pct}%",
                        detail=(
                            f"{self._fmt_dur(s.end)} of {self._fmt_dur(duration)} · "
                            f"{speed:.1f}x realtime · ETA {self._fmt_dur(remaining)}"
                        ),
                    )
                    if frac >= next_log:
                        self._log(
                            f"[{pct:3d}%] {self._fmt_dur(s.end)} / {self._fmt_dur(duration)} | "
                            f"elapsed {self._fmt_dur(elapsed)} | {speed:.1f}x realtime | "
                            f"ETA {self._fmt_dur(remaining)} | {len(segments)} segments"
                        )
                        next_log += step
                elif len(segments) % 25 == 0:
                    self._progress(
                        20, f"Transcribing... {len(segments)} segments",
                        detail=f"elapsed {self._fmt_dur(elapsed)}",
                    )
        else:
            self._progress(10, "Transcribing (openai-whisper)...",
                           detail="openai-whisper reports progress when the pass finishes.")
            self._log("openai-whisper is running (no live ETA — it finishes the whole file at once).")
            result = self.model.transcribe(audio_path, language=lang)
            all_segments = result.get("segments", [])
            total = len(all_segments)
            for idx, s in enumerate(all_segments, start=1):
                if stop_event is not None and stop_event.is_set():
                    cancelled = True
                    break
                segments.append({
                    "start": round(s["start"], 2),
                    "end": round(s["end"], 2),
                    "text": s["text"].strip(),
                })
                if total:
                    self._progress(
                        10 + int((idx / total) * 85),
                        f"Collecting segments... {int(idx / total * 100)}%",
                        detail=f"{idx} of {total} segments",
                    )
            detected_lang = result.get("language", self.language)
            self._log(f"Detected language: {detected_lang}")

        pass_elapsed = time.time() - t0
        self._log(f"Transcription pass finished in {self._fmt_dur(pass_elapsed)}.")

        if cancelled:
            self._log(
                f"Stopped by user after {len(segments)} segments "
                f"({self._fmt_dur(pass_elapsed)} elapsed)."
            )
            raise RuntimeError("Cancelled by user")

        if len(segments) == 0:
            self._log("No speech segments were detected. The audio may be silent or unsupported.")

        duration_sec = segments[-1]["end"] if segments else 0
        if duration_sec > 0 and pass_elapsed > 0:
            speed = duration_sec / pass_elapsed
            self._log(
                f"Speed: {speed:.1f}x realtime ({pass_elapsed:.0f}s processing for "
                f"{self._fmt_dur(duration_sec)} of audio, {len(segments)} segments)."
            )

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
            "app_version": APP_VERSION,
            "backend": self.backend,
            "device": self.device,
            "compute_type": self.compute_type,
            "model_size": self.model_size,
        }

        # Save JSON
        self._progress(96, "Saving files...", detail="Writing transcript JSON and minutes Markdown.")
        out_json = os.path.join(result["output_folder"], f"{meeting_name}_transcript.json")
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        self._log(f"Saved JSON transcript: {out_json} ({os.path.getsize(out_json) / 1024:.1f} KB)")

        # Save Markdown minutes
        out_md = os.path.join(result["output_folder"], f"{meeting_name}_minutes.md")
        with open(out_md, "w", encoding="utf-8") as f:
            f.write(self.to_markdown(result))
        self._log(f"Saved Markdown minutes: {out_md}")

        total_elapsed = time.time() - t_start
        self._progress(
            100, "Completed",
            detail=f"{len(segments)} segments · total {self._fmt_dur(total_elapsed)}",
        )
        self._log(f"All done in {self._fmt_dur(total_elapsed)}.")

        return result

    @staticmethod
    def _fmt_dur(seconds):
        """Format seconds as 1h 02m 03s / 2m 05s / 7s."""
        try:
            seconds = int(max(0, float(seconds)))
        except Exception:
            seconds = 0
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h {m:02d}m {s:02d}s"
        if m:
            return f"{m}m {s:02d}s"
        return f"{s}s"


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

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _prepare(result):
        """Return the values every exporter needs, with safe fallbacks."""
        duration = result.get("duration_seconds") or 0
        try:
            duration_txt = f"{round(float(duration) / 60, 1)} min"
        except Exception:
            duration_txt = "-"
        return {
            "name": result.get("meeting_name") or "Meeting",
            "date": result.get("meeting_date") or "-",
            "start": result.get("start_time") or "-",
            "end": result.get("end_time") or "-",
            "duration": duration_txt,
            "language": result.get("detected_language") or "-",
            "participants": ", ".join(result.get("participants") or []) or "-",
            "segments": result.get("segments") or [],
        }

    @staticmethod
    def export_docx(result, path):
        try:
            from docx import Document
            from docx.shared import Pt
        except Exception as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "python-docx is not installed. Run: pip install python-docx\n" + str(exc)
            )
        data = MeetingTranscriber._prepare(result)

        doc = Document()
        try:
            doc.styles["Normal"].font.name = "Calibri"
            doc.styles["Normal"].font.size = Pt(11)
        except Exception:
            pass

        doc.add_heading(f"Meeting Minutes — {data['name']}", 0)
        doc.add_paragraph(f"Date: {data['date']}   |   {data['start']} – {data['end']}")

        # Meeting details table
        doc.add_heading("1. Meeting Details", level=1)
        table = doc.add_table(rows=0, cols=2)
        table.style = "Table Grid"
        for key, value in [
            ("Meeting", data["name"]),
            ("Date", data["date"]),
            ("Start Time", data["start"]),
            ("End Time", data["end"]),
            ("Duration", data["duration"]),
            ("Language", data["language"]),
            ("Participants", data["participants"]),
        ]:
            row = table.add_row().cells
            row[0].text = key
            row[1].text = str(value)
            for run in row[0].paragraphs[0].runs:
                run.bold = True

        # Agenda
        doc.add_heading("2. Agenda", level=1)
        doc.add_paragraph("1. (Add agenda items here)")

        # Discussion / transcript
        doc.add_heading("3. Discussion / Perbincangan", level=1)
        if not data["segments"]:
            doc.add_paragraph("(No transcript available)")
        for seg in data["segments"]:
            p = doc.add_paragraph()
            p.add_run(f"[{MeetingTranscriber._fmt_ts(seg.get('start', 0))}] ").bold = True
            p.add_run(str(seg.get("text", "")).strip())

        # Decisions
        doc.add_heading("4. Decisions / Keputusan", level=1)
        doc.add_paragraph("• (Record decisions here)")

        # Action items
        doc.add_heading("5. Action Items / Tindakan", level=1)
        actions = doc.add_table(rows=1, cols=5)
        actions.style = "Table Grid"
        for cell, label in zip(actions.rows[0].cells, ["#", "Action", "Owner", "Due Date", "Status"]):
            cell.text = label
            for run in cell.paragraphs[0].runs:
                run.bold = True
        blank = actions.add_row().cells
        for cell, value in zip(blank, ["1", "", "", "", "Pending"]):
            cell.text = value

        # Next meeting
        doc.add_heading("6. Next Meeting", level=1)
        doc.add_paragraph("(Date / time of next meeting)")

        doc.add_paragraph()
        footer = doc.add_paragraph(
            "Prepared by Meeting Transcriber — https://github.com/rashidzainol/MeetingTranscipt"
        )
        try:
            for run in footer.runs:
                run.font.size = Pt(8)
                run.italic = True
        except Exception:
            pass

        doc.save(path)

    @staticmethod
    def _pdf_safe(text):
        """Core PDF fonts are Latin-1 only, so normalise unsupported characters."""
        text = str(text)
        replacements = {
            "\u2014": "-",
            "\u2013": "-",
            "\u2018": "'",
            "\u2019": "'",
            "\u201c": '"',
            "\u201d": '"',
            "\u2026": "...",
            "\u2022": "-",
            "\u00a0": " ",
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        return text.encode("latin-1", "replace").decode("latin-1")

    @staticmethod
    def export_pdf(result, path):
        try:
            from fpdf import FPDF
            from fpdf.enums import XPos, YPos
            from fpdf.fonts import FontFace
        except Exception as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "fpdf2 is not installed. Run: pip install fpdf2\n" + str(exc)
            )
        data = MeetingTranscriber._prepare(result)
        safe = MeetingTranscriber._pdf_safe

        class MinutesPDF(FPDF):
            def header(self):
                if self.page_no() == 1:
                    return
                self.set_font("Helvetica", "I", 8)
                self.set_text_color(130, 130, 130)
                self.cell(0, 8, safe(data["name"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                self.set_draw_color(220, 220, 220)
                self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
                self.ln(2)

            def footer(self):
                self.set_y(-15)
                self.set_font("Helvetica", "I", 8)
                self.set_text_color(130, 130, 130)
                self.cell(
                    0, 10,
                    safe(f"Page {self.page_no()}/{{nb}}  -  Meeting Transcriber"),
                    align="C",
                )

        pdf = MinutesPDF(orientation="P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.set_margins(15, 15, 15)
        pdf.alias_nb_pages()
        pdf.add_page()

        # Title
        pdf.set_font("Helvetica", "B", 18)
        pdf.set_text_color(43, 58, 103)
        pdf.multi_cell(0, 9, safe(f"Meeting Minutes - {data['name']}"))
        pdf.set_draw_color(43, 58, 103)
        pdf.set_line_width(0.6)
        pdf.line(15, pdf.get_y() + 1, 195, pdf.get_y() + 1)
        pdf.ln(4)
        pdf.set_text_color(0, 0, 0)

        def section(title):
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(43, 58, 103)
            pdf.cell(0, 8, safe(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(0, 0, 0)

        def body(text, h=5.5):
            pdf.set_font("Helvetica", size=10.5)
            pdf.multi_cell(0, h, safe(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Meeting details
        section("1. Meeting Details")
        pdf.set_font("Helvetica", size=10.5)
        for key, value in [
            ("Meeting", data["name"]),
            ("Date", data["date"]),
            ("Start Time", data["start"]),
            ("End Time", data["end"]),
            ("Duration", data["duration"]),
            ("Language", data["language"]),
            ("Participants", data["participants"]),
        ]:
            pdf.set_font("Helvetica", "B", 10.5)
            pdf.cell(33, 6.5, safe(f"{key}:"), new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.set_font("Helvetica", size=10.5)
            pdf.multi_cell(0, 6.5, safe(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Agenda
        section("2. Agenda")
        body("1. (Add agenda items here)")

        # Transcript
        section("3. Discussion / Perbincangan")
        if not data["segments"]:
            body("(No transcript available)")
        for seg in data["segments"]:
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.set_text_color(90, 90, 90)
            pdf.cell(
                0, 5.5,
                safe(f"[{MeetingTranscriber._fmt_ts(seg.get('start', 0))}]"),
                new_x=XPos.LMARGIN, new_y=YPos.NEXT,
            )
            pdf.set_text_color(0, 0, 0)
            body(seg.get("text", ""), h=5.5)
            pdf.ln(1)

        # Decisions
        section("4. Decisions / Keputusan")
        body("- (Record decisions here)")

        # Action items
        section("5. Action Items / Tindakan")
        pdf.set_font("Helvetica", size=9.5)
        with pdf.table(
            col_widths=(8, 62, 30, 30, 25),
            text_align=("CENTER", "LEFT", "LEFT", "LEFT", "CENTER"),
            line_height=6,
            headings_style=FontFace(emphasis="BOLD"),
        ) as table:
            header = table.row()
            for label in ["#", "Action", "Owner", "Due Date", "Status"]:
                header.cell(safe(label))
            row = table.row()
            for value in ["1", "", "", "", "Pending"]:
                row.cell(safe(value))

        # Next meeting
        section("6. Next Meeting")
        body("(Date / time of next meeting)")

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