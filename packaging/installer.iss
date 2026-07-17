#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#ifndef SourceDir
  #define SourceDir "..\build\release-work\Genshin_autoTTS"
#endif

#ifndef OutputDir
  #define OutputDir "..\build\release"
#endif

[Setup]
AppId={{1A31926E-3F10-4B0C-BABC-27772E90645E}
AppName=Genshin_autoTTS
AppVersion={#MyAppVersion}
AppPublisher=Genshin_autoTTS contributors
AppPublisherURL=https://github.com/uinaqx/Genshin_autoTTS
AppSupportURL=https://github.com/uinaqx/Genshin_autoTTS/issues
AppUpdatesURL=https://github.com/uinaqx/Genshin_autoTTS/releases/latest
DefaultDirName={localappdata}\Programs\Genshin_autoTTS
DefaultGroupName=Genshin_autoTTS
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=Genshin_autoTTS-Setup-x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Genshin_autoTTS.exe
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription=Genshin_autoTTS Windows installer
VersionInfoProductName=Genshin_autoTTS
VersionInfoProductVersion={#MyAppVersion}

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Genshin_autoTTS"; Filename: "{app}\Genshin_autoTTS.exe"
Name: "{autodesktop}\Genshin_autoTTS"; Filename: "{app}\Genshin_autoTTS.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\Genshin_autoTTS.exe"; Description: "Launch Genshin_autoTTS"; Flags: nowait postinstall skipifsilent
