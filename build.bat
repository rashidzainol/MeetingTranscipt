@echo off
setlocal
set VERSION=1.8.0
echo Building MeetingTranscriber v%VERSION%...
python -m pip install -r requirements.txt
pyinstaller --onefile --windowed --name "MeetingTranscriber-v%VERSION%" --icon "icon.ico" main.py
echo.
echo Build complete: dist\MeetingTranscriber-v%VERSION%.exe
pause
