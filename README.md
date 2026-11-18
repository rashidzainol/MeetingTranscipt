# Meeting Transcriber

A Windows desktop app that turns meeting recordings into a written transcript and a
ready-to-edit set of meeting minutes — in **English** or **Bahasa Malaysia**.

Pick an audio file, describe the meeting, press Start, then export the minutes to
**Word** or **PDF**.

**Version 1.10.0 · Last updated: 18 November 2026**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-lightgrey)
![Engine](https://img.shields.io/badge/Engine-faster--whisper-orange)
![License](https://img.shields.io/badge/License-MIT-green)

---

## System Requirements

Whisper is a **local AI speech model**, so transcription speed depends almost entirely
on your hardware. The app itself is light; the model does the hard work.

| | Minimum | Recommended | Best (fastest) |
|---|---|---|---|
| **OS** | Windows 10/11 64-bit | Windows 11 64-bit | Windows 11 64-bit |
| **CPU** | 4 cores (Intel/AMD) | 8+ cores, e.g. Core i7 / Ryzen 7 | 12+ cores, Core i9 / Ryzen 9 |
| **RAM** | 8 GB | 16 GB | 32 GB |
| **Storage** | 2 GB free | 5 GB free on SSD | 10 GB free on NVMe SSD |
| **GPU** | Not required | Optional NVIDIA GTX/RTX | NVIDIA RTX with CUDA 12 + cuDNN 9 |
| **Internet** | Needed once to download the model | — | — |

- The installed app takes about 250 MB. Each Whisper model is downloaded once and
  cached in `%USERPROFILE%\.cache\huggingface`.
- The **installer** version is recommended over the portable EXE: it starts faster and
  does not need to unpack itself every time.
- The app auto-detects an NVIDIA GPU. If CUDA/cuDNN are present it uses the GPU;
  otherwise it safely falls back to CPU.
- AMD and Intel graphics are not used by `faster-whisper`; those machines run on CPU
  (an AMD/Intel CPU is fine, just choose a smaller model).

---

## Performance — why Whisper is slow (and why it is not the app)

The application calls the Whisper speech model. Large models need a lot of computation
per second of audio. If transcription feels slow, the cause is the **model size plus
your CPU/GPU**, not the app.

### Model size vs speed vs accuracy

Approximate values for `faster-whisper` with int8 on a modern **8-core CPU**. Your
machine may be faster or slower.

| Model | Download | RAM needed | Speed (8-core CPU) | Accuracy |
|---|---|---|---|---|
| `tiny` | ~75 MB | ~1 GB | 15–30× realtime | Basic — fine for clear speech |
| `base` **(default)** | ~145 MB | ~1 GB | 8–15× realtime | Good for normal meetings |
| `small` | ~480 MB | ~2 GB | 4–8× realtime | Better for accents/noise |
| `medium` | ~1.5 GB | ~4 GB | 1.5–3× realtime | High, but slow on CPU |
| `large` | ~3 GB | ~6 GB | 0.7–1.5× realtime | Best; needs a strong CPU/GPU |

“8× realtime” means a 60-minute recording takes about 7–8 minutes. On a 4-core laptop
expect roughly half that speed.

### What makes Whisper faster

1. **GPU (biggest gain).** An NVIDIA RTX GPU with CUDA can be 10–30× faster than a CPU.
   Install CUDA 12 + cuDNN 9 and the app will use it automatically.
2. **More CPU cores.** Whisper scales well with cores. 8 cores are roughly twice as
   fast as 4.
3. **Smaller model.** `base` is typically 4–8× faster than `large` and is enough for
   normal meeting audio.
4. **faster-whisper backend.** The app uses `faster-whisper` (CTranslate2, int8), which
   is usually **3–4× faster than the original OpenAI Whisper** on the same CPU.
5. **SSD and free RAM.** Model loading and audio decoding are much quicker on an SSD.
6. **Close other heavy apps.** Browsers, Teams/Zoom and games compete for CPU and RAM.
7. **Set the language** (`en` or `ms`) instead of `auto` — detection adds a small
   overhead and can pick the wrong language on mixed audio.

### Practical tips for long recordings

- 1–2 hours: `base` or `small` is usually the best balance.
- 3 hours or more: use `base`, or split the audio into parts and transcribe separately.
- Do not choose `medium`/`large` on a laptop with 8 GB RAM — it will be slow and may
  run out of memory.
- Keep the laptop plugged in; Windows reduces CPU speed on battery.

---

## Features

- **Speech-to-text** with Whisper (`faster-whisper`, automatic CPU/GPU selection)
- **English / Bahasa Malaysia / auto-detect**
- **Meeting details form** — name, date picker, start time, participants
- **End time** calculated from the audio duration
- **Live progress** — percentage, audio processed, speed (× realtime), ETA, Stop button
- **Detailed processing log** (visible by default) with hardware information
- **Transcript editor** for fixing names and wording before export
- **Standard minutes template** — details, agenda, discussion, decisions, action items,
  next meeting
- **Export to Word (.docx) and PDF**
- **Update checker** using the GitHub Releases API
- **Copy Log / Log Folder** buttons for easy error reporting
- **Interactive installer** with Start Menu/desktop shortcuts and an uninstaller

---

## Download & Install

1. Open the [Releases](https://github.com/rashidzainol/MeetingTranscipt/releases) page.
2. Download the latest **`MeetingTranscriber-vX.Y.Z-Setup.exe`**.
3. Run the wizard: Welcome → License → Folder → Install → Finish.
4. Launch **Meeting Transcriber** from the Start Menu.

The installer does **not** need administrator rights and can be removed from
*Settings → Apps*. A portable single-file build (`...-Portable.exe`) is also attached
to each release.

> The installer is not code-signed, so Windows SmartScreen may show
> “Windows protected your PC” — choose **More info → Run anyway**. If Windows
> **Smart App Control** is enabled it can block the file completely; see
> **Logs & Troubleshooting**.

> The first transcription downloads the selected model from Hugging Face. An internet
> connection is needed once; later runs work offline.

---

## How to Use

1. **Browse** for the meeting recording (`.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`).
2. Fill in the **meeting name**, **date**, **start time**, and **participants**.
3. Choose a **model size** (start with `base`).
4. Choose the **language** (`auto`, `en`, `ms`) and press **▶ Start**.
5. Watch the **Progress** panel and the **Processing Log**.
6. When finished, use **📝 Editor** to correct the transcript, then **📄 Word** or
   **📑 PDF** to export the minutes.

Output files are written next to the audio file:

- `<meeting>_transcript.json` — segments with timestamps
- `<meeting>_minutes.md` — minutes in Markdown

Keyboard shortcuts: `Ctrl+O` browse, `F5` start, `Esc` stop.

---

## Logs & Troubleshooting

The log file is stored at:

```
%LOCALAPPDATA%\MeetingTranscriber\meeting_transcriber.log
```

It contains the app version, Windows version, CPU core count, RAM, model/backend,
audio duration, speed, ETA and any error traceback. Use **📂 Log Folder** to open it and
**📋 Copy Log** to copy everything when asking for help.

If Word/PDF export reports a missing library when running from source:

```powershell
pip install python-docx fpdf2
```

Common issues:

| Problem | What to do |
|---|---|
| “No Whisper backend found” | Run `pip install -r requirements.txt` |
| First run seems stuck | It is downloading the model; check the log |
| Very slow | Use a smaller model, or a GPU; see **Performance** |
| Out of memory | Use `tiny`/`base` and close other apps |
| Model download fails | Check internet/proxy; retry, or use a VPN |
| “Application Control policy has blocked this file” | Windows **Smart App Control** blocks unsigned apps. Open *Windows Security → App & browser control → Smart App Control* and turn it **Off**, then run the installer again. (Turning it off cannot be undone without reinstalling Windows.) |

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
meeting names and transcripts with non-Latin-1 characters.

### Build the Windows package

```powershell
python -m pip install pyinstaller
.\build.bat
```

`build.bat` produces:

- `dist\MeetingTranscriber-v1.10.0.exe` — portable one-file build
- `dist\installer_src\MeetingTranscriber\` — folder build used by the installer
- `release\MeetingTranscriber-v1.10.0-Setup.exe` — installer

Building the installer requires [Inno Setup 7](https://jrsoftware.org/isinfo.php)
(`winget install --id JRSoftware.InnoSetup.7 -e`).

---

## Project Structure

| File | Purpose |
|---|---|
| `main.py` | Tkinter GUI, logging, progress, update check, About dialog |
| `meeting_transcriber.py` | Whisper backend, timestamps, minutes template, Word/PDF export |
| `transcript_editor.py` | Transcript viewer / editor window |
| `version_check.py` | Version, release date, GitHub update checker |
| `installer/installer.iss` | Inno Setup script |
| `build.bat` | One-command build (portable + installer) |
| `tests/test_export.py` | Export smoke tests |

---

## Credits

Developed by **Rashid Zainol — JANN Sarawak**.

- [OpenAI Whisper](https://github.com/openai/whisper)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [python-docx](https://python-docx.readthedocs.io/) and [fpdf2](https://py-pdf.github.io/fpdf2/)
- [Inno Setup](https://jrsoftware.org/isinfo.php)

## License

MIT — see [LICENSE](LICENSE).

---

© 2026 Rashid Zainol — JANN Sarawak. All rights reserved.
