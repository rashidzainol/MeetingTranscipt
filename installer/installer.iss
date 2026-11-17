; Inno Setup script for Meeting Transcriber
; Build with: "C:\Users\<you>\AppData\Local\Programs\Inno Setup 7\ISCC.exe" installer.iss
;
; Expected build layout:
;   dist\installer_src\MeetingTranscriber\MeetingTranscriber.exe   (PyInstaller --onedir output)
;   dist\MeetingTranscriber-v1.9.0.exe                             (portable onefile, optional)

#define AppName "Meeting Transcriber"
#define AppVersion "1.9.0"
#define AppPublisher "Rashid Zainol - JANN Sarawak"
#define AppURL "https://github.com/rashidzainol/MeetingTranscipt"
#define AppExeName "MeetingTranscriber"

[Setup]
AppId={{7C2F5B1E-9A4D-4E2B-9C3F-1D5A7B8E2C41}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\release
OutputBaseFilename=MeetingTranscriber-v{#AppVersion}-Setup
SetupIconFile=..\icon.ico
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\{#AppExeName}.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64os
ArchitecturesAllowed=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
RestartApplications=no
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "..\dist\installer_src\MeetingTranscriber\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}.exe"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
