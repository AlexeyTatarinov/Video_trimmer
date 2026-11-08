; Inno Setup script for Video Trimmer. Build (from the repository root):
;   iscc /DAppVersion=0.3.0 installer\VideoTrimmer.iss
; Expects the PyInstaller output (with the ffmpeg\ folder) in dist\VideoTrimmer.
; Output: installer-out\VideoTrimmer-Setup-<version>.exe

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Video Trimmer"
#define AppExe "VideoTrimmer.exe"
#define ShellVerb "VideoTrimmer"
#define ProgId "VideoTrimmer.Video"

[Setup]
; Fixed AppId: keeps upgrades/uninstall tied to one entry. "{{" escapes the brace.
AppId={{6B0E8E57-3C41-4D0E-9B6B-7A1F6C2D9A34}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Video Trimmer
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes
OutputDir=..\installer-out
OutputBaseFilename=VideoTrimmer-Setup-{#AppVersion}
SetupIconFile=..\src\video_trimmer\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
; Checked by default (no "unchecked" flag).
Name: "shellmenu"; Description: "Add 'Trim with Video Trimmer' to the right-click menu and 'Open with'"; GroupDescription: "Explorer integration:"

[Files]
Source: "..\dist\VideoTrimmer\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; All registry data lives under HKCU\Software\Classes (no admin rights needed).
; No default program is changed: only a verb under SystemFileAssociations, an
; Applications entry, a private ProgID and "Open with" lists are written.
; Every key we create is removed on uninstall (uninsdeletekey / uninsdeletevalue);
; shared parent keys are removed only when they are left empty.
[Registry]
; ---- Applications\VideoTrimmer.exe (shown in "Open with") ----
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
; ---- private ProgID referenced from OpenWithProgids ----
Root: HKCU; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueName: ""; ValueData: "Video (Video Trimmer)"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueName: "FriendlyTypeName"; ValueData: "Video (Video Trimmer)"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu

; ---- .mp4 ----
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mp4\shell\{#ShellVerb}"; ValueType: string; ValueName: ""; ValueData: "Trim with {#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mp4\shell\{#ShellVerb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mp4\shell\{#ShellVerb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".mp4"; ValueData: ""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mp4"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mp4\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mp4\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mp4\OpenWithList"; Flags: uninsdeletekeyifempty; Tasks: shellmenu

; ---- .m4v ----
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.m4v\shell\{#ShellVerb}"; ValueType: string; ValueName: ""; ValueData: "Trim with {#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.m4v\shell\{#ShellVerb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.m4v\shell\{#ShellVerb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".m4v"; ValueData: ""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.m4v"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.m4v\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.m4v\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.m4v\OpenWithList"; Flags: uninsdeletekeyifempty; Tasks: shellmenu

; ---- .mkv ----
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mkv\shell\{#ShellVerb}"; ValueType: string; ValueName: ""; ValueData: "Trim with {#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mkv\shell\{#ShellVerb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mkv\shell\{#ShellVerb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".mkv"; ValueData: ""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mkv"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mkv\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mkv\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mkv\OpenWithList"; Flags: uninsdeletekeyifempty; Tasks: shellmenu

; ---- .mov ----
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mov\shell\{#ShellVerb}"; ValueType: string; ValueName: ""; ValueData: "Trim with {#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mov\shell\{#ShellVerb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mov\shell\{#ShellVerb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".mov"; ValueData: ""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mov"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mov\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mov\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mov\OpenWithList"; Flags: uninsdeletekeyifempty; Tasks: shellmenu

; ---- .avi ----
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.avi\shell\{#ShellVerb}"; ValueType: string; ValueName: ""; ValueData: "Trim with {#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.avi\shell\{#ShellVerb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.avi\shell\{#ShellVerb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".avi"; ValueData: ""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.avi"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.avi\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.avi\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.avi\OpenWithList"; Flags: uninsdeletekeyifempty; Tasks: shellmenu

; ---- .webm ----
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webm\shell\{#ShellVerb}"; ValueType: string; ValueName: ""; ValueData: "Trim with {#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webm\shell\{#ShellVerb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webm\shell\{#ShellVerb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".webm"; ValueData: ""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.webm"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.webm\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.webm\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.webm\OpenWithList"; Flags: uninsdeletekeyifempty; Tasks: shellmenu

; ---- .wmv ----
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.wmv\shell\{#ShellVerb}"; ValueType: string; ValueName: ""; ValueData: "Trim with {#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.wmv\shell\{#ShellVerb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.wmv\shell\{#ShellVerb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".wmv"; ValueData: ""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.wmv"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.wmv\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.wmv\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.wmv\OpenWithList"; Flags: uninsdeletekeyifempty; Tasks: shellmenu

; ---- .flv ----
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.flv\shell\{#ShellVerb}"; ValueType: string; ValueName: ""; ValueData: "Trim with {#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.flv\shell\{#ShellVerb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.flv\shell\{#ShellVerb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".flv"; ValueData: ""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.flv"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.flv\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.flv\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.flv\OpenWithList"; Flags: uninsdeletekeyifempty; Tasks: shellmenu

; ---- .mpg ----
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mpg\shell\{#ShellVerb}"; ValueType: string; ValueName: ""; ValueData: "Trim with {#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mpg\shell\{#ShellVerb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mpg\shell\{#ShellVerb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".mpg"; ValueData: ""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mpg"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mpg\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mpg\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mpg\OpenWithList"; Flags: uninsdeletekeyifempty; Tasks: shellmenu

; ---- .mpeg ----
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mpeg\shell\{#ShellVerb}"; ValueType: string; ValueName: ""; ValueData: "Trim with {#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mpeg\shell\{#ShellVerb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mpeg\shell\{#ShellVerb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".mpeg"; ValueData: ""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mpeg"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mpeg\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mpeg\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mpeg\OpenWithList"; Flags: uninsdeletekeyifempty; Tasks: shellmenu

; ---- .ts ----
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.ts\shell\{#ShellVerb}"; ValueType: string; ValueName: ""; ValueData: "Trim with {#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.ts\shell\{#ShellVerb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.ts\shell\{#ShellVerb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".ts"; ValueData: ""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.ts"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.ts\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.ts\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.ts\OpenWithList"; Flags: uninsdeletekeyifempty; Tasks: shellmenu

; ---- .mts ----
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mts\shell\{#ShellVerb}"; ValueType: string; ValueName: ""; ValueData: "Trim with {#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mts\shell\{#ShellVerb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mts\shell\{#ShellVerb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".mts"; ValueData: ""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mts"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mts\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mts\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mts\OpenWithList"; Flags: uninsdeletekeyifempty; Tasks: shellmenu

; ---- .m2ts ----
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.m2ts\shell\{#ShellVerb}"; ValueType: string; ValueName: ""; ValueData: "Trim with {#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.m2ts\shell\{#ShellVerb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.m2ts\shell\{#ShellVerb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".m2ts"; ValueData: ""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.m2ts"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.m2ts\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.m2ts\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.m2ts\OpenWithList"; Flags: uninsdeletekeyifempty; Tasks: shellmenu

; ---- .3gp ----
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.3gp\shell\{#ShellVerb}"; ValueType: string; ValueName: ""; ValueData: "Trim with {#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.3gp\shell\{#ShellVerb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.3gp\shell\{#ShellVerb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".3gp"; ValueData: ""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.3gp"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.3gp\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.3gp\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.3gp\OpenWithList"; Flags: uninsdeletekeyifempty; Tasks: shellmenu

; ---- .ogv ----
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.ogv\shell\{#ShellVerb}"; ValueType: string; ValueName: ""; ValueData: "Trim with {#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.ogv\shell\{#ShellVerb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.ogv\shell\{#ShellVerb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".ogv"; ValueData: ""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.ogv"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.ogv\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.ogv\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.ogv\OpenWithList"; Flags: uninsdeletekeyifempty; Tasks: shellmenu

; ---- .vob ----
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.vob\shell\{#ShellVerb}"; ValueType: string; ValueName: ""; ValueData: "Trim with {#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.vob\shell\{#ShellVerb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.vob\shell\{#ShellVerb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".vob"; ValueData: ""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.vob"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.vob\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.vob\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.vob\OpenWithList"; Flags: uninsdeletekeyifempty; Tasks: shellmenu

; ---- .mxf ----
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mxf\shell\{#ShellVerb}"; ValueType: string; ValueName: ""; ValueData: "Trim with {#AppName}"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mxf\shell\{#ShellVerb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mxf\shell\{#ShellVerb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".mxf"; ValueData: ""; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mxf"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mxf\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mxf\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: shellmenu
Root: HKCU; Subkey: "Software\Classes\.mxf\OpenWithList"; Flags: uninsdeletekeyifempty; Tasks: shellmenu
