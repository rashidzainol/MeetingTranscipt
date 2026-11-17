@echo off
setlocal
set VERSION=1.9.0
cd /d "%~dp0"

echo ============================================
echo  Building Meeting Transcriber v%VERSION%
echo ============================================

echo [1/4] Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo [2/4] Building portable one-file EXE...
pyinstaller --noconfirm --onefile --windowed --name "MeetingTranscriber-v%VERSION%" ^
  --icon "icon.ico" ^
  --hidden-import docx --hidden-import fpdf --hidden-import fpdf.fonts --hidden-import fpdf.enums ^
  main.py
if errorlevel 1 goto :failed

echo [3/4] Building app folder for the installer...
pyinstaller --noconfirm --onedir --windowed --name "MeetingTranscriber" ^
  --distpath "dist\installer_src" --workpath "build\installer" ^
  --icon "icon.ico" ^
  --hidden-import docx --hidden-import fpdf --hidden-import fpdf.fonts --hidden-import fpdf.enums ^
  main.py
if errorlevel 1 goto :failed

echo [4/4] Building installer...
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if not exist "%ISCC%" (
  echo.
  echo Inno Setup 7 not found. Install it with:
  echo    winget install --id JRSoftware.InnoSetup.7 -e
  echo The portable EXE and app folder are ready in dist\.
  goto :done
)
"%ISCC%" "installer\installer.iss"
if errorlevel 1 goto :failed

:done
echo.
echo Build complete.
echo   Portable : dist\MeetingTranscriber-v%VERSION%.exe
echo   Installer: release\MeetingTranscriber-v%VERSION%-Setup.exe
pause
exit /b 0

:failed
echo.
echo Build failed. Check the messages above.
pause
exit /b 1
