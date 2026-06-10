; UniEmail Agent installer

[Setup]
AppName=UniEmailAgent
AppVersion=0.2.0
DefaultDirName={localappdata}\Programs\UniEmailAgent
DefaultGroupName=UniEmailAgent
OutputDir=.
OutputBaseFilename=UniEmailAgent_Setup_v0.2.0
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
DisableDirPage=no
UninstallDisplayIcon={app}\UniEmailAgentApp.exe
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:";

[Files]
Source: "backend\dist\UniEmailAgentApp\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\UniEmailAgent"; Filename: "{app}\UniEmailAgentApp.exe"
Name: "{group}\Uninstall UniEmailAgent"; Filename: "{uninstallexe}"
Name: "{userdesktop}\UniEmailAgent"; Filename: "{app}\UniEmailAgentApp.exe"; Tasks: desktopicon

[Run]
Filename: "{cmd}"; Parameters: "/C npm install -g @anthropic-ai/claude-code --yes"; StatusMsg: "Installing Claude Code CLI..."; Flags: runhidden; Check: NpmAvailable
Filename: "{app}\_internal\playwright\driver\playwright.cmd"; Parameters: "install chromium"; StatusMsg: "Preparing browser runtime for university crawling..."; Flags: runhidden
Filename: "{app}\UniEmailAgentApp.exe"; Description: "Launch UniEmailAgent"; Flags: nowait postinstall skipifsilent

[Code]
var
  ApiKeyPage: TInputQueryWizardPage;

function JsonEscape(Value: string): string;
begin
  Result := Value;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True);
end;

function NpmAvailable: Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/C where npm', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

procedure InitializeWizard;
begin
  ApiKeyPage := CreateInputQueryPage(
    wpSelectDir,
    'Configure API Key',
    'Enter your DeepSeek API Key',
    'UniEmail Agent uses this key for Claude Code CLI and LLM-assisted crawling. The key is stored only on this computer under LocalAppData.'
  );
  ApiKeyPage.Add('DeepSeek API Key:', True);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ApiKeyPage.ID then begin
    if Trim(ApiKeyPage.Values[0]) = '' then begin
      MsgBox('Please enter a DeepSeek API Key before continuing.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ApiKey: string;
  EnvText: string;
  ConfigText: string;
  RuntimeDir: string;
begin
  if CurStep = ssPostInstall then begin
    ApiKey := Trim(ApiKeyPage.Values[0]);
    RuntimeDir := ExpandConstant('{localappdata}\UniEmailAgent');
    ForceDirectories(RuntimeDir);

    EnvText :=
      'DEEPSEEK_API_KEY=' + ApiKey + #13#10 +
      'DEEPSEEK_API_BASE=https://api.deepseek.com/v1' + #13#10 +
      'ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic' + #13#10 +
      'CLAUDE_CODE_SIMPLE=1' + #13#10;

    ConfigText :=
      '{' + #13#10 +
      '  "service_mode": "custom",' + #13#10 +
      '  "service_token": "",' + #13#10 +
      '  "deepseek_api_key": "' + JsonEscape(ApiKey) + '",' + #13#10 +
      '  "balance_yuan": 5.0' + #13#10 +
      '}' + #13#10;

    SaveStringToFile(ExpandConstant('{app}\.env'), EnvText, False);
    SaveStringToFile(RuntimeDir + '\config.json', ConfigText, False);
  end;
end;
