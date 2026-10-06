; ---------------------------------------------------------------------------
; School Manager - Windows installer (Inno Setup 6)
; Publisher: Ahmi software firm (established 2020)
;
; Bundles two core components as one product:
;   1. the School Manager application (PyInstaller onedir from Phase 5)
;   2. the WhatsApp bridge (whatsapp-service/ with its own Node runtime)
;
; School data (SQLite database, backups, license files, WhatsApp session)
; lives in %LOCALAPPDATA%\SchoolManager and is deliberately NOT touched by
; install, update or uninstall - a school never loses its records and never
; has to re-pair the WhatsApp phone after an update.
;
; Build:  ISCC.exe installer\SchoolManager.iss
; Output: build\installer\SchoolManager_Setup_v1.0.0.exe
; ---------------------------------------------------------------------------

#define MyAppName "School Manager"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Ahmi software firm"
#define MyAppExeName "SchoolManager.exe"
#define MyAppCopyright "Copyright (c) 2020-2026 Ahmi software firm"

[Setup]
; Stable AppId: updates and reinstalls find the same product (1-click update).
AppId={{A8F2D19E-6C31-4F20-B84A-91D0E49E01F8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://ahmisoftwarefirm.com
AppSupportURL=https://ahmisoftwarefirm.com/support
AppUpdatesURL=https://ahmisoftwarefirm.com/updates
AppCopyright={#MyAppCopyright}
; Control Panel / Windows Settings registration under the publisher name.
UninstallDisplayName={#MyAppName} - {#MyAppPublisher}
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoCompany={#MyAppPublisher}
VersionInfoCopyright={#MyAppCopyright}
VersionInfoDescription={#MyAppName} - School administration for Windows
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoTextVersion={#MyAppVersion}
; Per-machine install into Program Files.
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName} - {#MyAppPublisher}
DisableProgramGroupPage=yes
OutputDir=..\build\installer
OutputBaseFilename=SchoolManager_Setup_v{#MyAppVersion}
SetupIconFile=assets\SchoolManager.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
; Lets the QA loop run a per-user silent test install (/CURRENTUSER) without
; elevation; the default double-click install stays per-machine (admin).
PrivilegesRequiredOverridesAllowed=commandline
ArchitecturesInstallIn64BitMode=x64compatible
; Replace files that are in use by closing the app gracefully where possible.
CloseApplications=yes
RestartApplications=no
ChangesEnvironment=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; --- Core 1: the application (Phase 5 output, incl. obfuscated code) --------
Source: "..\build\exe\SchoolManager\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

; --- Core 2: the WhatsApp bridge (mandatory feature, with Node runtime) -----
; Staged by tools/build_installer.py: server.js, package.json, node_modules/
; and a private node.exe.  The WhatsApp *session* is never shipped - it is
; created per-school inside %LOCALAPPDATA%\SchoolManager\whatsapp-session.
Source: "..\build\installer-staging\whatsapp-service\*"; \
    DestDir: "{app}\whatsapp-service"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

; --- Customer quick-start guide --------------------------------------------
Source: "..\docs\QUICKSTART.txt"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; Pre-create the data folder with user-modify rights so the app (running as
; the logged-in user) can write its database, logs and WhatsApp session on
; first launch.  Never deleted by the uninstaller.
Name: "{localappdata}\SchoolManager"; Permissions: users-modify
Name: "{localappdata}\SchoolManager\whatsapp-session"; Permissions: users-modify

[Icons]
Name: "{group}\School Manager - {#MyAppPublisher}"; Filename: "{app}\{#MyAppExeName}"; \
    Comment: "School Manager - school administration (Ahmi software firm)"
Name: "{group}\Uninstall School Manager"; Filename: "{uninstallexe}"
Name: "{autodesktop}\School Manager - {#MyAppPublisher}"; Filename: "{app}\{#MyAppExeName}"; \
    Comment: "School Manager - school administration (Ahmi software firm)"; \
    Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Nothing: the data folder in %LOCALAPPDATA% survives uninstalls on purpose.
; (School records, backups, the license file and the WhatsApp session are
;  user data - only a manual delete removes them.)

[Code]
// Close a running School Manager before installing/uninstalling so files in
// {app} can be replaced.  The bridge (node.exe) is stopped by matching its
// command line, so unrelated node processes are never touched.
procedure CloseSchoolManager();
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{cmd}'), '/C taskkill /IM SchoolManager.exe /F /T >nul 2>&1',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{cmd}'),
       '/C powershell -NoProfile -Command "Get-CimInstance Win32_Process | ' +
       'Where-Object { $_.CommandLine -like ''*whatsapp-service*server.js*'' } | ' +
       'ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1500);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  CloseSchoolManager();
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    CloseSchoolManager();
end;
