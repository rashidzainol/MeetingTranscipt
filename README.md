# Meeting Transcriber

A simple Windows desktop app that turns meeting audio into a written transcript and
a ready-to-edit set of meeting minutes — in **English** or **Bahasa Malaysia**.

Built for everyday office use: pick an audio file, describe the meeting, press Start,
then export the result to **Word** or **PDF**.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Features

- **Speech-to-text** with Whisper (via `faster-whisper`, falls back to `openai-whisper`)
- **English / Bahasa Malaysia / auto-detect**
- **Meeting details form** — name, date picker, start time, participants
- **End time** calculated from the audio duration (or shown in the transcript)
- **Live progress** — percentage, current step, ETA, and a Stop button
- **Transcript editor** for fixing names and wording before export
- **Standard minutes template** — details, agenda, discussion, decisions, action items, next meeting
- **Export to Word (.docx) and PDF**
- **Update checker** using the GitHub Releases API
- **Copy Log / Log Folder** buttons so errors can be shared easily
- **Interactive installer** with Start Menu and desktop shortcuts plus an uninstaller

---

## Download & Install

1. Open the [Releases](https://github.com/rashidzainol/MeetingTranscipt/releases) page.
2. Download the latest **`MeetingTranscriber-vX.Y.Z-Setup.exe`**.
3. Run it and follow the wizard (choose folder, shortcuts, Install).
4. Launch **Meeting Transcriber** from the Start Menu.

The installer does **not** need administrator rights and can be removed later from
*Settings → Apps* like any other program.

A portable single-file build (`...-Portable.exe`) is also attached to each release if
you prefer not to install anything.

> First transcription downloads the Whisper model (about 75 MB for `base`) from
> Hugging Face, so an internet connection is needed once.

---

## How to Use

1. **Browse** for the meeting recording (`.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`).
2. Fill in the **meeting name**, **date**, **start time**, and **participants**.
3. Choose a **model size**:
   - `tiny` / `base` — fastest, good for clear recordings
   - `small` / `medium` — better accuracy, slower
   - `large` — best accuracy, needs a lot of RAM and time
4. Choose the **language** (`auto`, `en`, `ms`) and press **▶ Start**.
5. When finished, use **📝 Editor** to correct the transcript, then **📄 Word** or
   **📑 PDF** to export the minutes.

Output files are written next to the audio file:

- `<meeting>_transcript.json` — segments with timestamps
- `<meeting>_minutes.md` — the minutes in Markdown

---

## Logs & Troubleshooting

The log is written to:

```
%LOCALAPPDATA%\MeetingTranscriber\meeting_transcriber.log
```

Use **📂 Log Folder** to open it and **📋 Copy Log** to copy the contents when asking
for help.

If Word/PDF export reports a missing library when running from source:

```powershell
pip install python-docx fpdf2
```

---

## Run from Source

```powershell
git clone https://github.com/rashidzainol/MeetingTranscipt.git
cd MeetingTranscipt
python -m pip install -r requirements.txt
python main.py
```

### Run the tests

```powershell
python -m unittest discover -s tests -v
```

The suite checks that the Word and PDF exporters produce valid files, including
meeting names and transcripts that contain non-Latin-1 characters.

### Build the Windows package```powershell
python -m pip install pyinstaller
.\build.bat
```

`build.bat` produces:

- `dist\MeetingTranscriber-v1.9.0.exe` — portable one-file build
- `dist\installer_src\MeetingTranscriber\` — folder build used by the installer
- `release\MeetingTranscriber-v1.9.0-Setup.exe` — installer

Building the installer requires [Inno Setup 7](https://jrsoftware.org/isinfo.php).

---

## Project Structure

| File | Purpose |
|---|---|
| `main.py` | Tkinter GUI, logging, progress, update check, About dialog |
| `meeting_transcriber.py` | Whisper backend, timestamps, minutes template, Word/PDF export |
| `transcript_editor.py` | Transcript viewer / editor window |
| `version_check.py` | Current version + GitHub release checker |
| `installer/installer.iss` | Inno Setup script |
| `build.bat` | One-command build (portable + installer) |

---

## Credits

Developed by **Rashid Zainol — JANN Sarawak**.

- [OpenAI Whisper](https://github.com/openai/whisper)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [python-docx](https://python-docx.readthedocs.io/) and [fpdf2](https://py-pdf.github.io/fpdf2/)
- [Inno Setup](https://jrsoftware.org/isinfo.php)

## License

MIT — see [LICENSE](LICENSE).
