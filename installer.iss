; AI Trading Radar — Inno Setup Installer Script
; Build with Inno Setup Compiler (https://jrsoftware.org/isinfo.php)
;
; IMPORTANT: Before building, update the AppVersion below to match
; the current version in aitrader_bot/version.py.
;
; For auto-upgrade:
;   - AppId stays the SAME across versions → Inno detects existing install
;   - AppVersion changes → Inno offers to upgrade
;   - UsePreviousAppDir=yes → remembers install location

#define MyAppName "AI Trading Radar"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "AI Trading Radar"
#define MyAppURL "https://github.com/dimaslukman-rgb/ai-trading-radar"
#define MyAppExeName "AITradingRadar.exe"
#define MyAppUpdateURL "https://github.com/ai-trading-bot/ai-trading-radar/releases"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppUpdateURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=AITradingRadar_Setup_v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
DisableProgramGroupPage=yes

; ── Upgrade support ──────────────────────────────────────────────
UsePreviousAppDir=yes
UsePreviousGroup=yes
DisableDirPage=auto
DirExistsWarning=auto

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: checkedonce
Name: "autostart"; Description: "&Auto-start with Windows (recommended)"; GroupDescription: "Startup options:"; Flags: checkedonce

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "config.example.json"; DestDir: "{app}"; DestName: "config.json"; Flags: ignoreversion onlyifdoesntexist
Source: "data\*"; DestDir: "{app}\data"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Edit Config"; Filename: "{app}\config.json"
Name: "{group}\Log Folder"; Filename: "{localappdata}\AITradingRadar\logs"
Name: "{group}\Check for Updates"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--check-update"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Run {#MyAppName} now"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup: Boolean;
begin
  Result := True;
end;

function InitializeUninstall: Boolean;
begin
  Result := True;
end;

function GetCustomSetupExitCode: Integer;
begin
  Result := 0;
end;
