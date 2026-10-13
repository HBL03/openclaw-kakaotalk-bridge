#ifndef AppVersion
  #define AppVersion "0.1.0-dev.1"
#endif
#ifndef SourceRoot
  #define SourceRoot ".."
#endif

[Setup]
AppId={{FD85A107-932C-4BD7-A71B-BBC4A8D7F329}
AppName=OpenClaw KakaoTalk Local Bridge
AppVersion={#AppVersion}
AppPublisher=Hyeonbeen Lee
AppPublisherURL=https://github.com/HBL03/openclaw-kakaotalk-bridge
DefaultDirName={localappdata}\Programs\OpenClawKakaoLocal
DefaultGroupName=OpenClaw KakaoTalk Local Bridge
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#SourceRoot}\dist
OutputBaseFilename=openclaw-kakaotalk-bridge-{#AppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
LicenseFile={#SourceRoot}\LICENSE
UninstallDisplayIcon={app}\OpenClawKakaoLocal.exe
#ifdef PublicBuild
SignTool=bridge
SignedUninstaller=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Files]
Source: "{#SourceRoot}\dist\OpenClawKakaoLocal\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\OpenClaw KakaoTalk Local Bridge"; Filename: "{app}\OpenClawKakaoLocal.exe"
Name: "{group}\Uninstall"; Filename: "{uninstallexe}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "OpenClawKakaoLocal"; Flags: dontcreatekey uninsdeletevalue

[Run]
Filename: "{app}\OpenClawKakaoLocal.exe"; Description: "Open settings (monitoring is initially off)"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataPath: String;
begin
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent) then
  begin
    if MsgBox('Delete this Windows user''s bridge settings, pairing key and pending queue? WSL data is managed separately.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      DataPath := ExpandConstant('{localappdata}\OpenClawKakaoLocal');
      { Exact application-owned path only; never follows a configurable data-dir. }
      DelTree(DataPath, True, True, True);
    end;
  end;
end;
