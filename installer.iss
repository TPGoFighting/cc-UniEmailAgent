; UniEmail Agent — Inno Setup 安装包脚本
; 在项目根目录运行: ISCC installer.iss

#define MyAppName "UniEmail Agent"
#define MyAppVersion "2.1.0"
#define MyAppPublisher "UniEmail Team"
#define MyAppURL "https://github.com/uniemail/UniEmailAgent"
#define MyAppExeName "UniEmailAgentApp.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={userpf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=UniEmailAgent-Setup-{#MyAppVersion}
SetupIconFile=backend\static\favicon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式:"; Flags: checkedonce

[Files]
Source: "backend\dist\UniEmailAgentApp\UniEmailAgentApp.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "backend\dist\UniEmailAgentApp\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "backend\.env.example"; DestDir: "{app}"; Flags: ignoreversion
Source: "backend\write_config.py"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\UniEmailAgent"

[Code]
var
  ApiKeyPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  ApiKeyPage := CreateInputQueryPage(
    wpSelectDir,
    'Configure DeepSeek API Key',
    'Enter your DeepSeek API Key to power AI crawling.',
    'You can fill this now, or skip and configure later in Settings.' + #13#10 +
    'Key starts with sk-, get it from platform.deepseek.com/api_keys.'
  );
  ApiKeyPage.Add('DeepSeek API Key:', True);
  ApiKeyPage.Values[0] := '';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ApiKeyPage.ID then
  begin
    if ApiKeyPage.Values[0] = '' then
    begin
      if MsgBox('No API Key entered. You can configure it later in the app Settings.' + #13#10 +
                'Continue without key?', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDNO then
      begin
        Result := False;
        Exit;
      end;
    end
    else if Pos('sk-', ApiKeyPage.Values[0]) <> 1 then
    begin
      if MsgBox('API Key doesn''''t start with "sk-".' + #13#10 +
                'Use this key anyway?', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDNO then
      begin
        Result := False;
        Exit;
      end;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  EnvFile, AppDataDir, ConfigFile, PyExe, PyCmd: string;
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if (ApiKeyPage.Values[0] <> '') then
    begin
      EnvFile := ExpandConstant('{app}\.env');
      AppDataDir := ExpandConstant('{localappdata}\UniEmailAgent');
      ForceDirectories(AppDataDir);
      ConfigFile := AppDataDir + '\config.json';

      { 使用捆绑的 Python 脚本写入 UTF-8 文件，彻底避开 ANSI 编码问题 }
      PyExe := ExpandConstant('{app}\write_config.py');
      if FileExists(PyExe) then
      begin
        PyCmd := '"' + PyExe + '" "' + EnvFile + '" "' + ConfigFile + '" "' + ApiKeyPage.Values[0] + '"';
        Exec('python', PyCmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        if ResultCode <> 0 then
        begin
          { 后备：使用 py launcher }
          Exec('py', '-3 ' + PyCmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        end;
      end;

      { 后备：如果 Python 不可用，用 SaveStringToFile }
      if (ResultCode <> 0) or not FileExists(EnvFile) then
      begin
        SaveStringToFile(EnvFile,
          'DEEPSEEK_API_KEY=' + ApiKeyPage.Values[0] + #13#10 +
          'DEEPSEEK_API_BASE=https://api.deepseek.com/v1' + #13#10,
          False);
        SaveStringToFile(ConfigFile,
          '{' + #13#10 +
          '  "service_mode": "custom",' + #13#10 +
          '  "service_token": "",' + #13#10 +
          '  "deepseek_api_key": "' + ApiKeyPage.Values[0] + '",' + #13#10 +
          '  "balance_yuan": 5.00' + #13#10 +
          '}' + #13#10,
          False);
      end;
    end;

    { WebView2 check }
    if not RegKeyExists(HKEY_LOCAL_MACHINE,
      'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}') and
       not RegKeyExists(HKEY_CURRENT_USER,
      'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}') and
       not RegKeyExists(HKEY_LOCAL_MACHINE,
      'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}') then
    begin
      MsgBox('Note: Microsoft Edge WebView2 runtime not detected.' + #13#10 +
             'Download from https://go.microsoft.com/fwlink/p/?LinkId=2124703',
             mbInformation, MB_OK);
    end;
  end;
end;
