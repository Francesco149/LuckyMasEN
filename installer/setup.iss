; ===========================================================================
; setup.iss — English re-wrap of the SYGNAS "Lucky*Mas Desktop Accessory"
; (JP: らき☆マス デスクトップアクセサリ Ver1.00; originally Inno Setup 5.1.10).
;
; Consumes the reproducible patched tree out/patched/ (built by tools/build_patch.py
; from the user's OWN originals/ — never redistributed; see patch/manifest.toml).
; Build (ISCC under wine):
;   WINEPREFIX=~/.wine-iss wine "C:\IS5\ISCC.exe" "Z:\<repo>\installer\setup.iss"
; Output: out/iss-build/setup.exe  (contains SYGNAS bytes -> gitignored, never commit).
;
; Source paths are relative to this script's dir (ISCC SourceDir default).
; ===========================================================================

#define MyAppName "Lucky*Mas Desktop Accessory"
#define MyAppVer "1.00"
#define MyAppPublisher "SYGNAS"
#define MyAppURL "http://sygnas.jp/"
#define Src "..\out\patched"

[Setup]
; AppId is the ASCII uninstall key (kept *-free); AppName is the *-styled display name.
AppId=LuckyMas
AppName={#MyAppName}
AppVersion={#MyAppVer}
AppVerName={#MyAppName} Ver{#MyAppVer}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={pf}\SYGNAS\LuckyMas
DefaultGroupName=SYGNAS\LuckyMas
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\rakimas.ico
SetupIconFile={#Src}\app\rakimas.ico
OutputDir=..\out\iss-build
OutputBaseFilename=setup
Compression=lzma2
SolidCompression=yes
; XP target: Setup runs on Windows 2000 SP3 / XP and up.
MinVersion=5.0
PrivilegesRequired=admin

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Files]
; The app tree -> {app}.  Launch.ini.org (stale JP backup) is excluded.
Source: "{#Src}\app\*"; DestDir: "{app}"; Excludes: "launcher\Launch.ini.org"; Flags: recursesubdirs ignoreversion
; Screensavers -> system32 (the screensaver subsystem enumerates there).
Source: "{#Src}\sys\*.scr"; DestDir: "{sys}"; Flags: ignoreversion

[Icons]
; Start Menu group = SYGNAS\LuckyMas.  Launcher/calendar need cwd = their own dir
; (Launch.exe / gcal.exe LoadLibrary gcalcore.dll by name).
Name: "{group}\Lucky Mas Launcher";    Filename: "{app}\launcher\Launch.exe"; WorkingDir: "{app}\launcher"
Name: "{group}\Google Calendar";       Filename: "{app}\launcher\gcal.exe";   WorkingDir: "{app}\launcher"
Name: "{group}\iM@S Calculator";       Filename: "{app}\calc\WinCalcImas.exe";  WorkingDir: "{app}\calc"
Name: "{group}\Lucky Star Calculator"; Filename: "{app}\calc\WinCalcLucky.exe"; WorkingDir: "{app}\calc"
Name: "{group}\Calculator";            Filename: "{app}\calc\WinCalc.exe";      WorkingDir: "{app}\calc"
Name: "{group}\Copy Animation";        Filename: "{app}\copy\MinkIt.exe";       WorkingDir: "{app}\copy"
Name: "{group}\Wallpaper";             Filename: "{app}\wallpaper\wallpaper.html"
Name: "{group}\Display Properties";    Filename: "{sys}\desk.cpl"
Name: "{group}\ReadMe";                Filename: "{app}\ReadMe.txt"
Name: "{group}\SYGNAS Website";        Filename: "{app}\SYGNAS.url"
Name: "{group}\Uninstall Lucky Mas";   Filename: "{uninstallexe}"

[INI]
; Pin the launcher's menu targets to the actual install dir.  Launch.exe reads these absolute
; Exec paths via the ANSI API, so {app} (ASCII) keeps them locale-safe (goal #2).  Titles ship
; English in Launch.ini already (patch/manifest.toml text_keys).
Filename: "{app}\launcher\Launch.ini"; Section: "Launch"; Key: "Exec000"; String: "{app}\calc\WinCalcImas.exe"
Filename: "{app}\launcher\Launch.ini"; Section: "Launch"; Key: "Exec001"; String: "{app}\calc\WinCalcLucky.exe"
Filename: "{app}\launcher\Launch.ini"; Section: "Launch"; Key: "Exec002"; String: "{app}\launcher\gcal.exe"
Filename: "{app}\launcher\Launch.ini"; Section: "Launch"; Key: "Exec003"; String: "{app}\copy\MinkIt.exe"
Filename: "{app}\launcher\Launch.ini"; Section: "Launch"; Key: "Exec004"; String: "{app}\wallpaper\wallpaper.html"
Filename: "{app}\launcher\Launch.ini"; Section: "Launch"; Key: "Exec009"; String: "{sys}\desk.cpl"
; MinkIt's animation folder (no MinkIt.ini ships originally -> the EN install writes it; *.mink live here).
Filename: "{app}\copy\MinkIt.ini"; Section: "Path"; Key: "Folder"; String: "{app}\copy"

[Run]
Filename: "{app}\ReadMe.txt"; Description: "View the ReadMe"; Flags: postinstall shellexec skipifsilent nowait
