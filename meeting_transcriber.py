"""Meeting transcription engine (Whisper-based, supports EN/BM)."""

import os
import json
from datetime import datetime, timedelta


class MeetingTranscriber:
    def __init__(self, model_size="base", language="auto", progress_callback=None):
        self.model_size = model_size
        self.language = language  # 'en', 'ms', or 'auto'
        self.progress_callback = progress_callback
        self.model = None
        self._load_model()

    def _log(self, msg):
        if self.progress_callback:
            self.progress_callback(msg)

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

    def transcribe_meeting(self, audio_path, meeting_name, chunk_length_min=5,
                           meeting_date=None, start_time=None, participants=None):
        """Transcribe an audio file and return a structured result dict."""
        if meeting_date is None:
            meeting_date = datetime.now().strftime("%Y-%m-%d")
        if start_time is None:
            start_time = datetime.now().strftime("%H:%M")

        self._log(f"Transcribing: {os.path.basename(audio_path)}")

        lang = None if self.language == "auto" else self.language

        segments = []
        if self.backend == "faster":
            segs, info = self.model.transcribe(audio_path, language=lang, beam_size=5)
            for s in segs:
                segments.append({
                    "start": round(s.start, 2),
                    "end": round(s.end, 2),
                    "text": s.text.strip(),
                })
            detected_lang = info.language
        else:
            result = self.model.transcribe(audio_path, language=lang)
            for s in result.get("segments", []):
                segments.append({
                    "start": round(s["start"], 2),
                    "end": round(s["end"], 2),
                    "text": s["text"].strip(),
                })
            detected_lang = result.get("language", self.language)

        # Compute end time from audio duration (last segment end)
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
        lines.append(f"# Meeting Minutes — {result['meeting_name']}")
        lines.append("")
        lines.append(f"- **Date:** {result['meeting_date']}")
        lines.append(f"- **Start:** {result['start_time']}   **End:** {result['end_time']}")
        lines.append(f"- **Duration:** {round(result['duration_seconds']/60, 1)} min")
        lines.append(f"- **Language:** {result['detected_language']}")
        if result.get("participants"):
            lines.append(f"- **Participants:** {', '.join(result['participants'])}")
        lines.append("")
        lines.append("## Transcript")
        lines.append("")
        for seg in result["segments"]:
            ts = self._fmt_ts(seg["start"]) if False else MeetingTranscriber._fmt_ts(seg["start"])
            lines.append(f"[{ts}] {seg['text']}")
        lines.append("")
        lines.append("## Minutes / Action Items")
        lines.append("")
        lines.append("_(Fill in decisions and action items here.)_")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _fmt_ts(seconds):
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def set_progress_callback(self, cb):
        self.progress_callback = cb