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
; Copy all files and folders in the PyInstaller build directory to {app}
Source: "..\dist\Blnq\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Blnq"; Filename: "{app}\Blnq.exe"; IconFilename: "{app}\Blnq.exe"
Name: "{group}\{cm:UninstallProgram,Blnq}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Blnq"; Filename: "{app}\Blnq.exe"; Tasks: desktopicon; IconFilename: "{app}\Blnq.exe"

[Run]
Filename: "{app}\Blnq.exe"; Description: "{cm:LaunchProgram,Blnq}"; Flags: nowait postinstall skipifsilent

[Code]
var
  DownloadPage: TDownloadWizardPage;

procedure InitializeWizard();
begin
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), nil);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  if CurPageID = wpReady then
  begin
    DownloadPage.Clear;
    DownloadPage.Add('https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata', 'eng.traineddata', '');
    DownloadPage.Add('https://github.com/tesseract-ocr/tessdata/raw/main/ron.traineddata', 'ron.traineddata', '');
    DownloadPage.Add('https://github.com/tesseract-ocr/tessdata/raw/main/rus.traineddata', 'rus.traineddata', '');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
      except
        SuppressibleMsgBox(AddPeriod(GetExceptionMessage), mbCriticalError, MB_OK, IDOK);
        Result := False;
        Exit;
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  TessDataDir: String;
begin
  if CurStep = ssPostInstall then
  begin
    TessDataDir := ExpandConstant('{app}\tesseract_bin\tessdata');
    if not DirExists(TessDataDir) then
      ForceDirectories(TessDataDir);
    CopyFile(ExpandConstant('{tmp}\eng.traineddata'), TessDataDir + '\eng.traineddata', False);
    CopyFile(ExpandConstant('{tmp}\ron.traineddata'), TessDataDir + '\ron.traineddata', False);
    CopyFile(ExpandConstant('{tmp}\rus.traineddata'), TessDataDir + '\rus.traineddata', False);
  end;
end;
