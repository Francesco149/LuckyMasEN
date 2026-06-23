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
; Wizard art lives here, extracted from the user's OWN setup.exe via innounp (SYGNAS art -> NEVER
; committed/shipped; out/ is gitignored).  Build prereq:
;   wine innounp.exe -x -m -d<repo>\out\og-extract <repo>\originals\disc\setup.exe "embedded\*"
#define OGEmbed "..\out\og-extract\embedded"
; MS PGothic (msgothic.ttc) — BUILDER-supplied via tools/get_font.py (--ttf / --langpack / --windows /
; --from-system); we NEVER ship the font (out/ is gitignored). Bundled + installed by the [Code] below so
; the wizard renders the faithful 586x364 AND the app's serifs get their real face on an XP with no
; East-Asian language pack.  Build prereq: python3 tools/get_font.py --list-sources
#define FontFile "..\out\font\msgothic.ttc"
#if !FileExists(AddBackslash(SourcePath) + FontFile)
  #error MS PGothic not found at out\font\msgothic.ttc -- run: python3 tools/get_font.py --list-sources
#endif
; gcal-xp native fake-Google server (tools/gcal-xp) — installed + autostarted so the launcher's
; calendar/mail work locally out of the box.  Build prereq: tools/gcal-xp/build.sh (i686/XP EXE).
#define GcalSrv "..\tools\gcal-xp"
#if !FileExists(AddBackslash(SourcePath) + GcalSrv + "\gcalsrv.exe")
  #error gcalsrv.exe not found -- run: tools/gcal-xp/build.sh
#endif

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
; --- faithful appearance: the original's Lucky Star wizard art (classic full-image style) ---
WizardImageFile={#OGEmbed}\WizardImage0.bmp
WizardSmallImageFile={#OGEmbed}\WizardSmallImage0.bmp
; Show the art at native aspect (the original isn't horizontally squashed).
WizardImageStretch=no
; The original's classic FULL-SCREEN gradient background, with the app name painted top-left.
; Gradient sampled from the original screenshot: bright blue (top) -> dark blue (bottom).
WindowVisible=yes
BackColor=$00FB0000
BackColor2=$002A0000
AppCopyright=2007 SYGNAS
DisableWelcomePage=no
; Force the Select-Dir + Select-Start-Menu pages even on RE-install. Their default is 'auto', which
; SKIPS them when a prior install of the same AppId exists -> that was the "missing first steps"
; (2nd page jumped to the task) and the Ready memo showing only the shortcut.
DisableDirPage=no
DisableProgramGroupPage=no
AllowNoIcons=yes
AppMutex=http://sygnas.jp/doujin/luckymaster/
; Post-install info page = a clean, narrow ASCII page (was: the wide/mojibake readme).
InfoAfterFile=info_after.txt
OutputDir=..\out\iss-build
OutputBaseFilename=setup
Compression=lzma2
SolidCompression=yes
; XP target: Setup runs on Windows 2000 SP3 / XP and up.
MinVersion=5.0
PrivilegesRequired=admin

[Languages]
; Custom EN .isl carrying MS PGothic 9 / Title 29 / Welcome 12 — drives the faithful 586x364 wizard
; (the stock compiler:Default.isl = Tahoma 8 -> a smaller 503-wide wizard). PGothic is made available
; by the [Code] AddFontResource below, so this size holds even on an XP with no East-Asian fonts.
Name: "en"; MessagesFile: "luckymas-en.isl"

[Messages]
; Show the "(D)" accelerator explicitly like the JP original (the English default puts it as a
; plain underlined "&Don't"; the JP shows it in parens).
NoProgramGroupCheck2=Don't create a Start Menu folder (&D)

[Tasks]
; The original offered a desktop shortcut for the launcher.
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; The app tree -> {app}.  Launch.ini.org (stale JP backup) is excluded.
Source: "{#Src}\app\*"; DestDir: "{app}"; Excludes: "launcher\Launch.ini.org"; Flags: recursesubdirs ignoreversion
; Screensavers -> system32 (the screensaver subsystem enumerates there).
Source: "{#Src}\sys\*.scr"; DestDir: "{sys}"; Flags: ignoreversion
; MS PGothic — bundled (dontcopy) so [Code] can AddFontResource it for the wizard + install it to {fonts}.
Source: "{#FontFile}"; DestDir: "{tmp}"; Flags: dontcopy
; gcal-xp server + its editable request-logic script -> {app}\gcal-xp (the cert is embedded in the EXE).
Source: "{#GcalSrv}\gcalsrv.exe"; DestDir: "{app}\gcal-xp"; Flags: ignoreversion
Source: "{#GcalSrv}\gcalsrv.lua"; DestDir: "{app}\gcal-xp"; Flags: ignoreversion
; Pre-seed the calendar account (captured post-login) so the launcher's calendar check works out of the
; box with NO login prompt -- a MISSING gcal.dat made the original launcher hang on the check (frozen
; mascot, no network call). The local server ignores credentials, so this throwaway blob is universal
; and not machine-bound (no DPAPI header). These are OUR seed files, not SYGNAS originals.
Source: "seed\gcal.ini"; DestDir: "{app}\launcher"; Flags: ignoreversion
Source: "seed\gcal.dat"; DestDir: "{app}\launcher"; Flags: ignoreversion

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
; The local fake-Google server: a Start-Menu entry + autostart (tray) for every user on login.
; --no-cert because the installer already trusted the cert (the [Run] --install-cert step below).
Name: "{group}\Fake Google server (gcal-xp)"; Filename: "{app}\gcal-xp\gcalsrv.exe"; Parameters: "--no-cert"; WorkingDir: "{app}\gcal-xp"
Name: "{commonstartup}\gcal-xp";              Filename: "{app}\gcal-xp\gcalsrv.exe"; Parameters: "--no-cert"; WorkingDir: "{app}\gcal-xp"
Name: "{group}\ReadMe";                Filename: "{app}\ReadMe.txt"
Name: "{group}\SYGNAS Website";        Filename: "{app}\SYGNAS.url"
Name: "{group}\Uninstall Lucky Mas";   Filename: "{uninstallexe}"
; Desktop shortcut (the original's optional task).
Name: "{userdesktop}\Lucky Mas Launcher"; Filename: "{app}\launcher\Launch.exe"; WorkingDir: "{app}\launcher"; Tasks: desktopicon

[INI]
; Pin the launcher's menu targets to the actual install dir.  Launch.exe reads these absolute
; Exec paths via the ANSI API, so {app} (ASCII) keeps them locale-safe (goal #2).  Titles ship
; English in Launch.ini already (patch/manifest.toml text_keys).
; --- out-of-the-box defaults (owner-requested) ---
; A default mascot (Konata Izumi) so one appears immediately; her folder = the launcher dir (the .Xvi).
Filename: "{app}\launcher\Launch.ini"; Section: "Data"; Key: "Folder"; String: "{app}\launcher"
Filename: "{app}\launcher\Launch.ini"; Section: "Data"; Key: "Chara"; String: "konata.Xvi"
; Check the (local) Google calendar on startup -- safe now that the account is pre-seeded (no hang).
Filename: "{app}\launcher\Launch.ini"; Section: "Calendar"; Key: "Boot"; String: "1"
; The "you've got mail" bubble opens this email client (Outlook Express ships on every XP).
Filename: "{app}\launcher\Launch.ini"; Section: "Mail"; Key: "Client"; String: "{pf}\Outlook Express\msimn.exe"
Filename: "{app}\launcher\Launch.ini"; Section: "Launch"; Key: "Exec000"; String: "{app}\calc\WinCalcImas.exe"
Filename: "{app}\launcher\Launch.ini"; Section: "Launch"; Key: "Exec001"; String: "{app}\calc\WinCalcLucky.exe"
Filename: "{app}\launcher\Launch.ini"; Section: "Launch"; Key: "Exec002"; String: "{app}\launcher\gcal.exe"
Filename: "{app}\launcher\Launch.ini"; Section: "Launch"; Key: "Exec003"; String: "{app}\copy\MinkIt.exe"
Filename: "{app}\launcher\Launch.ini"; Section: "Launch"; Key: "Exec004"; String: "{app}\wallpaper\wallpaper.html"
Filename: "{app}\launcher\Launch.ini"; Section: "Launch"; Key: "Exec009"; String: "{sys}\desk.cpl"
; MinkIt's animation folder (no MinkIt.ini ships originally -> the EN install writes it; *.mink live here).
Filename: "{app}\copy\MinkIt.ini"; Section: "Path"; Key: "Folder"; String: "{app}\copy"
; (The calendar account gcal.ini + gcal.dat are shipped as files in [Files] above -- pre-seeding the
; credential blob is what stops the original launcher hanging on the first calendar check.)

[Run]
; (1) Trust the server's www.google.com/localhost cert, as admin, into LocalMachine\Root — silent,
;     no protected-root modal (the cert is embedded in gcalsrv.exe).  (2) Start the server now, as
;     the logged-in user, so its tray icon appears in their session (it autostarts on later logins
;     via the {commonstartup} shortcut above).  The launcher's calendar/mail are already pointed at
;     localhost (host->localhost binpatch), so clicking them reaches this server.
Filename: "{app}\gcal-xp\gcalsrv.exe"; Parameters: "--install-cert"; Flags: runhidden waituntilterminated; StatusMsg: "Trusting the local server certificate..."
Filename: "{app}\gcal-xp\gcalsrv.exe"; Parameters: "--no-cert"; WorkingDir: "{app}\gcal-xp"; Flags: nowait runasoriginaluser skipifsilent

[Code]
(* MS PGothic delivery (font is BUILDER-supplied -- see the .iss header + tools/get_font.py):
   (1) InitializeSetup AddFontResources the bundled msgothic.ttc so the WIZARD scales to MS PGothic ->
       586x364 even on an XP with no East-Asian language pack (proven Session 10: a bundled font lifts
       the wizard 503->586 via that path);  (2) post-install it installs permanently to the Fonts dir
       (unless already present) so the APP serifs (CreateFontA "MS PGothic") render right too. *)
const
  FONT_REG = 'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts';
  FONT_KEY = 'MS Gothic & MS PGothic & MS UI Gothic (TrueType)';

function AddFontResource(lpFileName: AnsiString): Integer;
  external 'AddFontResourceA@gdi32.dll stdcall';

function PGothicPresent(): Boolean;
begin
  Result := FileExists(ExpandConstant('{fonts}\msgothic.ttc'))
            or RegValueExists(HKLM, FONT_REG, FONT_KEY);
end;

function InitializeSetup(): Boolean;
begin
  ExtractTemporaryFile('msgothic.ttc');
  AddFontResource(ExpandConstant('{tmp}\msgothic.ttc'));   // wizard gets MS PGothic -> 586x364
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var Dest: String;
begin
  if (CurStep = ssPostInstall) and not PGothicPresent() then
  begin
    Dest := ExpandConstant('{fonts}\msgothic.ttc');
    FileCopy(ExpandConstant('{tmp}\msgothic.ttc'), Dest, False);
    RegWriteStringValue(HKLM, FONT_REG, FONT_KEY, 'msgothic.ttc');
    AddFontResource(Dest);
  end;
end;
