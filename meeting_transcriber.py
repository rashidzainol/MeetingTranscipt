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