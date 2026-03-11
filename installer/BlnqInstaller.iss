[Setup]
; App Information
AppName=Blnq
AppVersion=1.0
AppPublisher=Blnq
DefaultDirName={autopf}\Blnq
DefaultGroupName=Blnq
UninstallDisplayIcon={app}\Blnq.exe
Compression=lzma2
SolidCompression=yes
OutputDir=..\dist
OutputBaseFilename=BlnqInstaller
SetupIconFile=..\resources\icons\app_icon.ico
PrivilegesRequired=admin
DisableProgramGroupPage=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Copy the main distribution file to the installation directory
Source: "..\dist\Blnq.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Blnq"; Filename: "{app}\Blnq.exe"; IconFilename: "{app}\Blnq.exe"
Name: "{group}\{cm:UninstallProgram,Blnq}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Blnq"; Filename: "{app}\Blnq.exe"; Tasks: desktopicon; IconFilename: "{app}\Blnq.exe"

[Run]
Filename: "{app}\Blnq.exe"; Description: "{cm:LaunchProgram,Blnq}"; Flags: nowait postinstall skipifsilent
