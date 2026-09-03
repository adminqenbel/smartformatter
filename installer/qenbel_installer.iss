; =====================================================================
;  QenBel Smart Formatter — Inno Setup Script
;  Builds professional Windows setup executable: QenBel-Smart-Formatter-Setup.exe
; =====================================================================

#define MyAppName "QenBel Smart Formatter"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "QenBel Technologies"
#define MyAppURL "https://www.qenbel.com"
#define MyAppExeName "QenBelSmartFormatter.exe"
#define MySourceDir "..\dist\QenBelSmartFormatter"
#define MyOutputDir "..\dist\installer"
#define MyIconFile "..\Logo\app_icon.ico"

[Setup]
; Unique application GUID for upgrade detection across versions
AppId={{E4A28B31-9F22-4D39-A33A-1B8DF12A7C34}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Default installation directory: C:\Program Files\QenBel\Smart Formatter
DefaultDirName={autopf}\QenBel\Smart Formatter
DefaultGroupName=QenBel
DisableProgramGroupPage=yes

; Elevated privileges required for Program Files installation
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible

; Compression configuration
Compression=lzma2/ultra64
SolidCompression=yes

; Installer output configuration
OutputDir={#MyOutputDir}
OutputBaseFilename=QenBel-Smart-Formatter-Setup
SetupIconFile={#MyIconFile}
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

; Modern styling
WizardStyle=modern
DisableWelcomePage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Complete application payload from PyInstaller distribution
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#MyIconFile}"; DestDir: "{app}\Logo"; Flags: ignoreversion

[Icons]
; Start Menu shortcut: QenBel -> Smart Formatter
Name: "{autoprograms}\QenBel\Smart Formatter"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\Logo\app_icon.ico"
; Desktop shortcut (checked by default)
Name: "{autodesktop}\Smart Formatter"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\Logo\app_icon.ico"; Tasks: desktopicon

[Run]
; Launch application option on finish
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,Smart Formatter}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up any temporary files inside the app dir without touching user data in %APPDATA%
Type: files; Name: "{app}\*.log"
