# Next builds — calendar emulator + XP remote probe

Two builds greenlit 2026-06-21 to enable autonomous, no-physical-access work on the XP test box.
Both are dev-box-side to write; the test rig (below) is in place to test them against real XP.
**This doc is self-contained** (written before a `/clear`) — it captures the RE + design needed to execute.

## Operational context — reaching & driving the box
- The **XP test box** runs ONE OS at a time, reachable only while it is in its NixOS state.
- It can be flipped into XP and back, booting XP exactly once; any XP shutdown/reboot returns to NixOS.
- **Cold-mount the XP disk** is available only while the box is in NixOS / XP cold. XP install root →
  `…/Program Files/SYGNAS/らき☆マス/{copy,launcher,calc,wallpaper}`.
- A driver/tooling kit is staged on the box's disk for offline install.
- Offline registry-hive edits are available while the box is in NixOS / XP cold.

## Build 1 — Calendar synthetic test-board (start here)
Make the launcher's calendar (and mail) speech bubbles fire on command, to verify every translated
bubble renders + check overflow. Later: a real local calendar backend ("proxy to a local thing").

**Protocol the launcher speaks** (RE'd from `gcalcore.dll` / `gcal.exe` / `Launch.exe`; WinINet, host
`www.google.com`, 2007 ClientLogin + GData Atom). ⚠️ **CORRECTED 2026-06-22 by live-test (see
`re-notes.md` §Session 2): ClientLogin is HTTPS, the feeds are plain HTTP.** The session-1 "all plain
`http://`, no cert" was wrong — gcal.exe opens TLS for the login (WinINet **12157 = secure-channel
error** when it can't), period-correct for 2007 Google. So the emulator needs **HTTPS on :443 for
ClientLogin** (self-signed `www.google.com` cert, **XP-trusted**, **XP-SP3-era TLS** = TLS1.0 + AES-CBC),
plus the **HTTP feeds** (already built + working):
- `POST https://www.google.com/accounts/ClientLogin`  body `Email=%s&Passwd=%s&service=cl&source=sygnas-gcal-0.1`
  → respond `SID=x\nLSID=x\nAuth=<token>\n` (it only reads `Auth=`). **← the one open piece (HTTPS).**
- every feed request carries header `Authorization: GoogleLogin auth=<token>`.
- `GET http://www.google.com/calendar/feeds/default/allcalendars/full` → Atom calendar **list**
  (an `<entry>` with the calendar `<title>` + a `<link href=…>` to the event feed; parser also reads `gCal:color`).
- event feed `GET …` → Atom **events**: parser reads **`gd:when` (with the `startTime` attr)**, `gd:where`,
  `<title>`. ≥1 event → `SerifCallenderSchedule` (titles fill `<%SCHEDULE%>`); empty → `SerifCallenderNone`.
- (low priority) add-event deep-link to the browser: `http://www.google.com/calendar/event?action=TEMPLATE&dates=…`.
- **Mail = POP3** (`Launch.exe`): `USER %s` / `PASS %s` / `STAT` → `+OK <n> <size>`. n=0 → `SerifMailNone`,
  n>0 → `SerifMailCheck`, connect/login refused → `SerifMailError`.

**Speech triggers** — right-click menu `(&M)`=Mail check, `(&C)`=Calendar check (the rest = settings/exit):

| bubble | how the test-board forces it |
|---|---|
| `SerifCallenderSchedule` | event feed returns ≥1 event for "today" |
| `SerifCallenderNone` | event feed returns empty |
| `SerifCallenderError` | ClientLogin error, or 403/500 on the feed |
| `SerifCallenderNoAccount` | app-side: blank the GCal ID in `gcal.ini` (no server call) |
| `SerifMailCheck` / `None` / `Error` | POP3 `STAT` n>0 / n=0 / refuse the connection |
| `SerifNewVersion` | only if the app's update check sees a newer build (low priority; could fake its update URL) |

**Design:** stdlib Python in `tools/gcal-emu/` — one HTTP server (ClientLogin + the 2 feeds) + a tiny POP3
server, with a **scenario selector** (env var / control file / path) to choose the response set and thus the
bubble. **First-cut + a request LOGGER**, so the first real-XP run captures the exact event-feed URL/params +
the XML the parser actually needs, then we lock the responses. Redirect: XP `hosts` `www.google.com →
<emu-host-IP>` (⚠️ also blackholes real google.com browsing on XP — fine for a retro box; toggle when
testing). **⚠️ corrected: run on a SEPARATE always-on box, NOT the XP box** — the XP box runs
one OS at a time, so it's offline while XP is booted (and XP reuses its NIC/lease). Needs port 80 free.

## Build 2 — XP remote probe (screen capture + push) — cold-loop
Push files to XP + observe (screenshots) with no physical access. Robust design
that reuses the proven cold-mount + boot mechanism and needs **no live network agent**:
1. Cold-mount XP, write the inputs (patched files) + a task descriptor.
2. Flip the box into XP.
3. XP **autologons** → a **Startup orchestrator** runs the task: launch the app, fire
   actions, **NirCmd `savescreenshot`** → `C:\probe\out\`, then reboot → back to NixOS.
4. Cold-mount XP again, read `C:\probe\out\` → analyze.

**Pieces to stage (all offline-installable now while XP is cold):**
- **NirCmd** — NOT in the kit; fetch from nircmd.com (Playwright if the DL is gated) → `C:\probe\nircmd.exe`.
- **Autologon** — the SOFTWARE hive's Winlogon key (`AutoAdminLogon=1` etc.).
- **Startup orchestrator** — a batch in `…\Documents and Settings\All Users\Start Menu\Programs\Startup\`
  that, **only when a flag file exists** (so normal boots aren't hijacked), runs `C:\probe\task.cmd`
  + screenshots + reboots.
- **Orchestrator** — a script doing steps 1–4 (mount/write/arm/reboot; on return mount/read).

**Optional later upgrade (live agent):** portable sshd (Bitvise WinSSHD) installed on first boot via the
orchestrator → live SFTP+exec on running XP (no reboot per change). Defer until the cold-loop works.

## State at this `/clear` (2026-06-21)
- **LuckyMas:** 22-char EN launcher translation **deployed** to XP (originals backed up;
  owner confirmed names + one speech line render in
  English). Formats MINK/ACZ/PACKDATA cracked; `tools/` = `sygnas_unpack.py` / `sygnas_repack.py` /
  `build_launcher_en.py`; `patch/launcher/*.ini`. Calc `.nut` + `.mink` sprite codecs deferred (don't gate TL).
- **Shutdown SOLVED:** Creative Audigy autostarts (`CTSysVol` + `Module Loader/DLLML`) parked → instant
  (revert: re-merge from `Run-LMparked`, or restore the SOFTWARE-hive backup).
  `verbosestatus=1` + per-user app-kill timeouts (2000/1000/AutoEndTasks=1) also set.
- **One-shot boot mechanism done + validated.**
- **SMBus INF deployed but the boot "new hardware" wizard still appears** — needs a manual Device-Manager
  install from the on-disk chipset-inf kit, or it's a *different* undriven device (iGPU/xHCI → BIOS-disable). Deferred.
- **Open LuckyMas TL surface:** PE-resource UI strings (dialogs/menus/string-tables, lang 1041 → `lief`),
  `Launch.ini` titles + wallpaper HTML (trivial text); then route A/B lock-in.

## ✅ Built 2026-06-21 (both builds, this session)
Wire format **confirmed from the binaries** (extracted the UTF-16LE strings — the build is MFC-Unicode
WinINet): `POST /accounts/ClientLogin` `Email=%s&Passwd=%s&service=%s&source=%s` → `Auth=`; `GET
/calendar/feeds/default/allcalendars/full` → Atom list w/ a `<link href=>` event feed; the feed reads
`gd:when@startTime`/`gd:where`/`title`; mail = POP3 `USER/PASS/STAT`. (`gcal.ini`/`gcal.dat` configs;
add-event `…/calendar/event?action=TEMPLATE&dates=%4d%02d%02d/…`.)

- **Build 1 — gcal-emu** → `LuckyMasterEN/tools/gcal-emu/` (`gcal_emu.py` + README). Stdlib HTTP
  (ClientLogin + both Atom feeds) + POP3, scenario selector (env + control file re-read per request →
  flip bubbles live) + a verbatim request LOGGER. **Self-tested on every scenario** (curl + a POP3
  client): schedule/none/error, mail check/none/error/refuse. ⚠️ **runs on a SEPARATE always-on box,
  not the XP box** (the XP box IS XP while XP runs); needs port 80 free + on the same LAN.
- **Build 2 — XP remote probe** (`xp-probe.sh` + `xp/*.cmd|.reg` + README) — lives in the Windows XP
  hardware-build repo. NirCmd staged to the kit (`nircmd.exe`, 32-bit verified). **Validated on the real
  cold disk (no reboot):** the mount guard, case-insensitive resolver, install, status, `hosts on|off`,
  `autologon on|off` (with readback), and `check-admin`. Disk left clean (autologon off, no redirect, no flag).

**One open step:** the first full cold-loop `arm → reboot → collect` (reboots the box into XP). Gated on
an owner go-ahead. Recommended first run **owner-supervised** (skip autologon, log in by hand once);
enable autologon for hands-off runs after the loop is proven. Runbook → the probe README.

### Hosting + the XP-local direction (2026-06-21)
The emulator can't run on the XP box itself (it *is* XP during the run), so it's wired onto a
**separate always-on box behind its reverse proxy**: a localhost service on port 8091 + a plain-HTTP
`http://www.google.com` vhost → it. XP's hosts redirect points `www.google.com` at that box. Committed +
eval/config-validated; **needs a deploy to go live.** Calendar-only (POP3 can't be reverse-proxy-fronted →
mail deferred).

**Build 3 (future, owner-requested):** a **user-friendly XP-local** emulator the end user runs on their
own XP box (`hosts www.google.com → 127.0.0.1`) to enjoy the mascots' calendar/mail with no Google account
— so it must be **native (no Python on XP)**: the protocol is tiny (HTTP/1.0 + POP3) → a small Win32 C
build (mingw-w64, XP subsystem) is the target, written with confidence from the confirmed wire format +
whatever the request logger captures on the first real run.

## ✅ Session 2 (2026-06-22) — live-tested; one open piece (HTTPS ClientLogin)
- **Live-control infra built + proven** (the "optional live agent", done — details in the probe README):
  a tiny **HTTP agent** on XP (runs in the interactive session → real screenshots) + **SMB** for clean
  deploys. The Bitvise-sshd idea was a dead end (deep config rabbit hole) → replaced. This is what made the
  live recon possible, **no cold-loop reboots**.
- **gcal-emu reachable from XP** (the always-on box deployed; hosts-redirect verified; gcal.exe launches +
  prompts for an account; the **HTTP feeds are ready**).
- **⛔ Open piece — HTTPS ClientLogin (see the corrected protocol above + `re-notes.md` §Session 2):**
  gcal.exe does **TLS** for `/accounts/ClientLogin` (12157). Build an HTTPS `:443` endpoint for
  `www.google.com` with an **XP-trusted self-signed cert + XP-SP3 TLS** (TLS1.0/AES-CBC). Then the feeds
  follow → the Serif bubbles fire. Ghidra-xref the JP error string in `gcalcore.dll` to pin whether the
  cert must be trusted vs cert-errors-ignored.

## ▶ Session 3 (2026-06-22) — PIVOT: build the native XP-local server (Build 3 is now THE path)

Owner-directed: **stop hosting the emulator on a separate LAN box / coercing modern TLS — build the
server natively on XP itself** (the end-user deliverable, was "Build 3, future"). Why it's strictly better:
- **TLS becomes trivial by construction.** On XP the server speaks **Schannel** and gcal.exe's client is
  **WinINet** — the *same* 2007 stack → the handshake is period-accurate with no SECLEVEL hacks, no
  "will Go/Python negotiate XP's handshake", no ancient ciphers to coerce: they're already there.
- **The remote-hosting route kept fighting infra:** the always-on box's reverse proxy **wildcard-binds
  `*:80`/`*:443`**, so even a secondary IP can't take `:443`. On XP, `hosts → 127.0.0.1` and our server owns
  `127.0.0.1:{80,443,110}` with nothing else there → the whole hosting apparatus evaporates.
- It's the actual product (no Google account) and kills the separate-always-on-box requirement + the
  POP3-can't-be-reverse-proxy-fronted limitation in one move.

**De-risked this session — the XP-era handshake works:** a TLS1.0 + RSA-kx **AES128-CBC-SHA** client (XP
SP3's exact capability) against our **SHA-1/RSA-2048 self-signed `www.google.com`** cert completes and
returns `Auth=` (local OpenSSL proof; the gcal-emu `--https` listener + `certs/` + `make-xp-cert.sh`).
So XP's WinINet will handshake our cert; the native Schannel server reproduces the same.

**Target architecture — one self-contained Win32 EXE (i686, XP subsystem):**
- plain sockets for **HTTP feeds (:80)** + **POP3 (:110)** — trivial C (the live HTTP agent proves the
  socket scaffolding; the response logic ports straight from `gcal_emu.py`, kept as the protocol oracle).
- **Schannel** for **HTTPS `/accounts/ClientLogin` (:443)** — the one fiddly piece
  (`AcquireCredentialsHandle` → `AcceptSecurityContext` token loop → `Encrypt/DecryptMessage`); only
  debuggable on XP via the live agent (no local loop / debugger). Raw Schannel honors "use XP's own
  ciphers"; **fallback** = statically link mbedTLS (portable/testable on Linux, bigger EXE) only if
  Schannel server-side fights us.
- cert in-process: bundle the cert+key as `.pfx` → **`PFXImportCertStore`** gives Schannel its server
  credential (no system store needed); **`CertAddEncodedCertificateToStore(ROOT,…)`** installs the public
  cert so WinINet trusts it. **Install into Root by default** (WinINet won't trust self-signed otherwise;
  harmless if gcal.exe ignored cert errors → no separate trust-probe needed).
- first-run/installer: `hosts: www.google.com → 127.0.0.1`, drop+autostart the EXE (Startup).

**Next steps:** (1) make the `.pfx`; (2) plain-socket HTTP/POP3 core (port `gcal_emu.py` responses to C);
(3) Schannel ClientLogin handshake + in-proc cert install; (4) i686-mingw build (via
`nix … pkgsCross.mingw32.buildPackages.gcc`), deploy to XP, drive gcal.exe via the agent, capture
the Serif bubbles. The remote-hosted Python path is **retired for the deliverable, kept as the oracle**.

## ✅ Session 4 (2026-06-22) — native server BUILT + Schannel PROVEN on real XP
Steps 1–3 + the build of step 4 are **done**: `tools/gcal-xp/gcalsrv.c` (one self-contained 80 KB i686 EXE)
serves HTTP feeds :80 + POP3 :110 (Winsock) + **HTTPS ClientLogin :443 (Schannel)**, cert embedded as an
XP-legacy PKCS#12 (`cert_pfx.h`). Cross-built via `build.sh` (mingw + nix), deployed + driven on
**a real XP box via SMB-exec**. **Validated live:** a real XP WinINet client (`MSXML2.XMLHTTP` =
gcal.exe's stack, `test/clientlogin.vbs`) completes the **Schannel handshake**, **trusts** the self-signed
cert, and gets `Auth=` from ClientLogin (`STATUS=200`); HTTP feeds + POP3 also verified. Full build log,
the five bugs fixed (legacy-PKCS12, mcfgthread/XP-safety, protected-root modal, handshake-crash, SYSTEM
keyset), and the SMB-exec-not-the-agent operating rule → [`re-notes.md`](re-notes.md) §"Session 4".

**Remaining:** (A) ✅ **embedded-Lua migration DONE + validated** (same session) — Lua 5.4 statically linked,
all request logic in `gcalsrv.lua` (C keeps sockets+Schannel+POP3+framing); re-tested on XP, byte-identical to
the C version. Next under this: a real local-calendar backend (script edit). (B) ✅ **end-to-end DONE** —
drove the real launcher, captured `SerifCallenderSchedule` + `SerifCallenderNone` (→ `docs/screenshots/`,
README gallery; findings in `re-notes.md` §Session 4). (C) unattended cert install + first-run installer.

## ▶ Next session (post-/clear): host→localhost patch + finish the translation
Owner will be **present for live UI testing** (drive the launcher by hand — much faster than blind nircmd
automation). Server side is done + validated; this phase is the patch + the rest of the text.

1. **Patch the host `www.google.com` → `localhost`** so XP keeps real internet (no `hosts` blackhole). The host
   is a **wide (UTF-16LE) string in `gcalcore.dll`** (confirmed via `strings -e l`); `localhost` (9) ≤
   `www.google.com` (14) → in-place patch, NUL-pad the tail. ⚠️ **The embedded cert is `CN=www.google.com`** —
   if the client connects to `localhost`, WinINet's TLS CN check fails. So **regenerate the cert as
   `CN=localhost`** (+ SAN `127.0.0.1`) in `make-xp-cert.sh`, re-run `embed-pfx.sh`, rebuild. (Or test first
   whether gcal ignores cert errors — if so, host patch alone suffices.) Then drop the `hosts` line. RE the
   exact `InternetConnect`/URL construction in `gcalcore.dll` to confirm host vs full-URL strings before patching.
2. **Finish the EN translation surface** (RE order from `re-notes.md` §Session 1): PE-resource UI strings
   (dialogs/menus/string-tables, lang 1041 → `lief`) in the four exes + the 4 `.scr`; `Launch.ini` `Title###`
   + `MinkIt.ini` + the wallpaper HTML + `お読みください.txt` (trivial text). The launcher serifs are already
   done (`patch/launcher/*.ini`). Calc `.nut` strings are behind an un-cracked codec (deferred).
3. **POP3 mail bubble** — `Launch.ini` `[Mail]` is empty (`Client=`, `Boot=0`); needs a configured POP3
   client/host to drive `SerifMail*` against gcalsrv :110. RE how Launch.exe builds the POP3 host.
4. Silent (no-modal) cert install (certutil/registry) + a one-click first-run installer (hosts + Startup).

XP driving recap (CLAUDE.md): commands via **SMB-exec**; GUI launch via
`nircmd exec show <fullpath>` (the agent wedges on `start`); **screenshots via PrtScn→clipboard** (the mascot is
a layered window `nircmd savescreenshotfull` can't capture). Driver: `lm.cmd` (the on-XP launcher driver).

## ✅ Session 5 (2026-06-22) — reproducible patch system + translation wins + host→localhost
Owner-directed pivot in *method*: every patch now flows through one reproducible, audited pipeline, building
toward the chosen deliverable — an **English installer re-wrapped from the user's own `setup.exe`**.
Architecture → [`patch-system.md`](patch-system.md); RE detail → [`re-notes.md`](re-notes.md) §Session 5.

- **Pipeline built:** `patch/manifest.toml` (what we patch) + `tools/build_patch.py` (mirror
  `originals/installed/`→`out/patched/`, apply ops, emit `PATCH-LOG.txt`). Reproducible; 22 `.Xvi` selftest 22/0.
- **Translated (display text):** Launch.ini menu titles, the readme, the wallpaper picker UI. Locale-safety
  rule applied (app-read text = pure ASCII; readme = UTF-8+BOM; HTML = UTF-8).
- **host→localhost DONE (build side):** `binpatch` rewrote the wide host in **both** `gcalcore.dll` (×2) and
  `gcal.exe` (×3, incl. the add-event deep-link) — whole NUL-terminated strings, size-preserving. Server
  matched: `gcalsrv.lua` localhost event-feed link + cert regenerated **CN=localhost** (+SAN); `gcalsrv.exe`
  rebuilt; `clientlogin.vbs` now defaults to localhost.
- **Deferred + recorded** (flip `active=true` later): install-root path rewrite, `.mink`/`.scr`/JPG renames,
  MinkIt copy-path, autorun, PE-resource strings.

### ▶ Live test runbook (owner-driven — loop in the owner for the GUI)
Box is in XP (SMB-exec) or NixOS (cold-mount). Deploy from `out/patched/`:
1. Copy the patched launcher (`out/patched/app/launcher/*` — patched `gcalcore.dll` + `gcal.exe` + EN `.Xvi`
   + `Launch.ini`) to the install (or `C:\lm` via `lm.cmd setup`), and the rebuilt `tools/gcal-xp/gcalsrv.exe`
   to `C:\gcal-xp\`.
2. **Remove the `www.google.com` line from `C:\WINDOWS\system32\drivers\etc\hosts`** (the whole point — no
   blackhole). `localhost` already resolves to 127.0.0.1.
3. Start `gcalsrv.exe` (installs the CN=localhost cert into Root on first run — owner OKs the protected-root
   modal once, or use a silent install; see Session 4 notes).
4. Headless TLS check: `cscript //nologo C:\gcal-xp\clientlogin.vbs` → expect `URL=https://localhost/...`,
   `STATUS=200`, `Auth=EMU_TEST_TOKEN` (proves localhost TLS + the new cert is trusted).
5. Launch the launcher → right-click → Calendar check → the **`SerifCallenderSchedule`** bubble fires reading
   from localhost. Confirm: English menu titles; real google.com still browsable in IE (no blackhole).

### Next major stage — English installer re-wrap
Consume `out/patched/`: `innoextract` the user's own `setup.exe` → drop in the patched tree → translate the
Inno script/UI (`[Languages]` + custom messages) + pin an English `{app}` path (`…\SYGNAS\LuckyMas`) →
recompile with **ISCC under wine** → an English `setup.exe`. Adds the Inno-compiler toolchain (not yet in the
flake). This is where the deferred install-root rename + path rewrite activate.

## ✅ Session 6 (2026-06-22) — ALL PE-resource translation done
Every resource-translatable, user-visible string is now English (surgical `pe_res` op; sizes unchanged, PEs
valid; owner-validated on real XP). Detail → [`re-notes.md`](re-notes.md) §"PE-resource translation".
- **Launch.exe**: right-click menus (IDR_MAINMENU/IDR_ITEMMENU) + dialogs (SETUPDLG/APPNAMEDLG/NEWNAMEDLG).
- **MinkIt.exe**: About/Preview/Setup dialogs (+ Preview label relayout via the new geometry-override).
- **WinCalc.exe**: menu + dialogs (MFC string table skipped — boilerplate; binary not launched anyway).
- Found N/A: themed calcs `WinCalcImas/Lucky` = `.nut`-scripted (no PE menus/dialogs); `.scr` have no
  translatable PE strings (dropdown name = filename → deferred rename).
- Tooling added: `tools/pe_res.py` (dump + surgical RT_MENU/RT_DIALOG patch + DLGTEMPLATE rebuilder +
  index-based geometry overrides). **Never use `lief.write()`** — it rebuilds the PE and crashes XP.

## ✅ Session 7 (2026-06-22) — binary / hardcoded-string TL DONE + `.Xvi` ASCII pass
All four handoff TODOs done (full detail → [`re-notes.md`](re-notes.md) §"Session 7"):
- New tool **`tools/scan_jp.py`** (cp932 + UTF-16 JP scanner; NUL-terminated-literal extraction, PE-section
  aware, noise filters) — `strings` can't see cp932. **`binpatch` gained `encoding="cp932"`** (1-byte NUL,
  SJIS `old` ↔ ASCII `new`).
- **Patched** (all `n=1`, size-preserving, reproducible, verified both directions): **MinkIt.exe** (14 —
  tray menu, the 5 event-type combo labels, Preview `(none)`/`(unk.)` defaults + `%s Preview`, messages),
  **MinkIt.dll** (1), **Launch.exe** (16 — incl. the **pin-arrow tooltip** `Drop an app on this button`,
  dialog titles, confirm/validation MsgBoxes, `・・・`→`...`), **gcal.exe** (9 cp932 image errors + 9 wide
  status/error/prompt), **gcalcore.dll** (3 wide errors). ⚠️ **wide budget is in CHARS** (EN usually longer
  than JP) → only wide strings padded by embedded ASCII (`%d`/`Result Code`) fit; pure-status → `Loading...`.
- **MinkIt Preview Title/Author = the hardcoded `(無題)`/`(不明)` defaults, NOT `.mink` metadata** — the
  `info` chunk is a shared codec table (`mink-format.md`), so no `.mink` data patch.
- **`.Xvi` ☆→ASCII pass** fixed at the generator (`build_launcher_en.py`): comment-missing-`;` tolerance
  (amimami), removed MT-junk `→`/`♪`, global `☆/★/♪`→`~` + fullwidth→ASCII, + a **pure-ASCII assert** guard.
  All 22 INIs pure ASCII; `.Xvi` Ini round-trips byte-exact.
- **Left as-is (recorded):** the `CreateFontA` facenames `ＭＳ Ｐゴシック`/`ＭＳ ゴシック` (not displayed
  text; changing risks serif rendering → **live-test if "MS PGothic" resolves** before touching); MFC
  AppWizard boilerplate + `TODO: <ファイルの説明>` VERSIONINFO placeholder (installer/version-stamp stage).

## ✅ Session 8 (2026-06-22) — host→localhost VALIDATED on real XP (agent-less) + ops cheatsheet
Operated **agent-less** (agent down; SMB only). Closed Session 5's loose end: the `host→localhost` +
`CN=localhost` cert path is now **proven on the box**, not just "build side done". Found XP running a
**stale** `gcalsrv.exe` (`CN=www.google.com`) while source/cert were already `CN=localhost` (the EXE is a
gitignored artifact → drifted). Rebuilt → redeployed → proved end-to-end: `clientlogin.vbs` →
`https://localhost` → `STATUS=200` + `Auth=`, server `handshake complete`, cert installed **silently as
SYSTEM** into both Root stores, `hosts` carries **no** google redirect. New: **an XP-ops cheatsheet**
(the agent-less SMB-only recipe — launching persistent EXEs, capturing their output, the pitfalls, and the
gcalsrv lifecycle). Detail → [`re-notes.md`](re-notes.md) §"Session 8".
**Live GUI test PASSED (owner-driven):** the `SerifCallenderSchedule` bubble fires through the real launcher,
the serif font renders clean (⇒ the `ＭＳ Ｐゴシック` facename stays JP, no patch), and the Session-7 EN
strings are confirmed (menus, pin tooltip, mail-interval validation, delete confirm). **+2 follow-up fixes
(done):** (a) GoogleAccount `DIALOG/129` `pe_res` in **gcal.exe + gcalcore.dll** → "Google Account Settings" /
"Cancel"; (b) star convention — **NAMES → `*`** (`Lucky*Mas`, `Lucky*Star`), **decorative serif tics → `~`**,
filenames `*`-free. **Deferred polish (owner-flagged, pre-existing JP bug):** a spurious empty app-launcher
menu on left-click — investigate after the translation/installer stage.

## ▶ Next session (post-/clear) — live-test the binary TL, then the installer re-wrap
Translation surface is now **complete** (PE-resource + hardcoded + serifs all EN; only the deferred
facenames/boilerplate/`.nut`-codec calc text remain). Two fronts:
1. **Owner-driven live test on real XP** (the fast path — loop the owner in): deploy `out/patched/` to the
   box, then eyeball that the new EN renders — MinkIt **tray menu** (Options/Exit) + the
   **Setup "Event type" combo** + **Preview** defaults; Launch.exe **pin-arrow tooltip** + rename/delete
   confirms + the **Settings validation** ("Mail check interval must be between 1 and 600."); gcal.exe
   status/errors. **Watch the serif font** — confirm the JP `ＭＳ Ｐゴシック` facename still renders the
   speech bubbles on the box; if it falls back ugly, patch it to the Latin "MS PGothic" (cp932 binpatch,
   16B→10B fits) and re-test (this is the one held-back string).
2. **English installer re-wrap** (the chosen deliverable): `innoextract` the user's own `setup.exe` →
   drop in `out/patched/` → translate the Inno script (`[Languages]` + custom messages) + pin `{app}`=
   `…\SYGNAS\LuckyMas` → recompile with **ISCC under wine**. Activates the deferred renames/path-rewrite
   (install-root, `.mink`/`.scr`/JPG, autorun) + the VERSIONINFO/FileDescription fix. Adds the Inno
   toolchain to the flake (not yet there).

**Deploy/drive recipe:** deploy to the XP box, with the live agent for GUI/screenshots. MinkIt needs its
`MinkIt.dll` + `.mink` alongside the exe — push them from `originals/installed/app/copy/`, + a `MinkIt.ini`
(`[Path]Folder=…`).

## ✅ Session 9 (2026-06-22) — English installer re-wrap (Inno) BUILT + faithful-wizard investigation
The chosen deliverable. An English `setup.exe` re-wrapped from the user's own disc `setup.exe`. **Built,
installs correctly on real XP** (owner-tested: `{pf}\SYGNAS\LuckyMas`, EN shortcuts, launcher/calendar/MinkIt
all work). Remaining = the *faithful wizard look* (in progress) + the JP-path rename. The live agent is up,
so screenshots work (`nircmd savescreenshotfull` for a normal window; the installer is NOT a layered window).

### Toolchain (all under wine, prefix `~/.wine-iss`)
- **ISCC** installed at: `C:\IS5` (5.6.1 unicode), `C:\IS559` (5.5.9), `C:\IS5110` (**5.1.10 = the original's
  exact version**). Run: `WINEPREFIX=~/.wine-iss wine "C:\IS5110\ISCC.exe" "Z:<repo>/installer/setup.iss"`.
- **innounp** at `out/iss-build/innounp/innounp.exe` — decompiles the OG `setup.exe`: `-x -m` extracted the
  original `install_script.iss` + `embedded\{WizardImage0.bmp,WizardSmallImage0.bmp,InfoAfter.txt,jp.isl}`
  → `out/og-extract/`. **The wizard BMPs are SYGNAS art → NEVER committed** (gitignored `out/`; the `.iss`
  references them there, re-extract from the user's own `setup.exe` at build time — prereq noted in the `.iss`).
- IS installers cached in `out/iss-build/` (`is561u.exe`, `is559.exe`, `is5110.exe`); innounp via bsdtar (RAR5).
- **TODO: make this reproducible in the flake** (pin the IS + innounp downloads; a `tools/extract-wizard-art.sh`).

### The `.iss` — `installer/setup.iss` (+ `installer/info_after.txt`)
Reconstructed (innoextract has no `.iss`; innounp gave the original to copy from). Has: `[Setup]` AppName
`Lucky*Mas Desktop Accessory`, AppId=LuckyMas, `{pf}\SYGNAS\LuckyMas`, **WindowVisible=yes + BackColor
`$00FB0000`→`$002A0000`** (the full-screen blue gradient sampled from the OG screenshot), WizardImage art,
WizardImageStretch=no, AppMutex, AllowNoIcons, **AppCopyright=2007 SYGNAS** (shows bottom-right), InfoAfterFile;
`[Languages]` EN Default.isl; `[Messages]` NoProgramGroupCheck2 with the `(D)` accel; `[Tasks]` desktopicon;
`[Icons]` the 10 Start-Menu shortcuts (from the OG) + desktop + uninstall; **`[INI]`** pins Launch.ini Exec###
+ MinkIt.ini Folder to `{app}` (Launch.exe reads absolute ANSI paths → `{app}` is ASCII). `DisableDirPage=no`
+ `DisableProgramGroupPage=no` (default `auto` SKIPS them on re-install → that was the "missing first steps").
Currently targets **IS 5.6.1**; the `[Code]` wizard-resize was REMOVED (dead end — see below).

### ⭐ THE WIZARD-SIZE FINDING (the current open item) — it's the FONT, not the IS version or [Code]
- OG (JP) wizard = **586×364**; ours (English) = **503×392** (owner-measured). NOT a `[Code]`/version thing
  (the OG `.iss` has no `[Code]`; IS 5.5.9 & 5.1.10 both render 503 with the English Default.isl).
- **ROOT CAUSE:** Inno scales the whole wizard to the `[LangOptions]` dialog font. `jp.isl` =
  **`DialogFontName=ＭＳ Ｐゴシック` (MS PGothic), `DialogFontSize=9`** (+ Title 29, Welcome 12); English
  `Default.isl` = Tahoma size 8. → a custom EN `.isl` carrying the JP fonts + English text renders **586×364,
  owner-confirmed "matches 1:1"** (test file: `out/iss-build/luckymas-en.isl` = a copy of 5.1.10's Default.isl
  with `[LangOptions]` set to `DialogFontName=MS PGothic / DialogFontSize=9 / TitleFontName=MS PGothic /
  TitleFontSize=29 / WelcomeFontName=MS PGothic / WelcomeFontSize=12`; smoke `out/iss-build/smoke_font.iss`).
- **⛔ THE OPEN QUESTION (owner is testing):** **does it work on an XP WITHOUT East-Asian language support
  (no MS PGothic)?** If the font is absent, GDI substitutes it — and the substitute's metrics (not MS
  PGothic's) likely drive the size → probably back to ~503 (i.e. the faithful size would only appear on
  systems that have the JP font). **Owner is booting a stock-XP box (NO lang pack) to test** whether
  MS PGothic exists there and whether the installer still matches.
- **NOT yet isolated: size-9 vs the font-NAME.** Untested: does *Tahoma 9* (a font present everywhere) alone
  give 586, or is it MS PGothic's specific metrics? If size-9-alone works → no font dependency (use any font
  at 9). First thing to try post-clear.
- **Options if the font dependency is real:** (a) ship/embed MS PGothic (licensing + size), (b) `[Code]`-FORCE
  the 586×364 layout *and reposition every inner control* (the removed `[Code]` only moved the outer frame so
  the white panel/buttons didn't follow — see the `eninstaller.png` symptom), (c) accept a locale-dependent
  size, (d) the owner's idea: "ship with JP-locale fonts but English text in a way that doesn't break on EN
  locale." The owner wants a deep dive: capture the Win32 window-layout API calls (JP vs EN) and binary-patch
  to match, if needed.

### Remaining installer work
1. **Resolve the font/size** per the stock-XP-box result + the Tahoma-9 test (above). Then bake the chosen
   `.isl` into `setup.iss` (`[Languages] MessagesFile=`).
2. **Rename the JP file paths** (owner-approved; also goal #2 ASCII). Needed if we stay ANSI 5.1.10; optional
   if we use Unicode 5.6.1 (which handles JP filenames natively — **note: since the SIZE is font-driven, IS
   5.6.1 Unicode + the font `.isl` also yields 586×364, so the version downgrade may be unnecessary**). The JP
   files in `out/patched`: **84 wallpaper JPGs** `らき☆マス_<artist>_<WxH>.jpg` + the **~96 `<a href>`/`<img src>`
   refs in `app/wallpaper/wallpaper.html`** (rewrite in lockstep) + **4 `.scr`** (manifest deferred renames →
   ASCII). Artist romaji is derivable from the ASCII `img/thumb_<key>.jpg` keys (araki/arata/asaba/azuma/
   herada/iso/minamo/miso/miyabi/serip/tanaka/uni/yone + GUNP/ISO already ASCII) by their HTML grouping.
3. **Port `setup.iss` to IS 5.1.10** *if* staying on it: 5.1.10 rejects `DisableWelcomePage` (welcome always
   shown), needs `AppVerName`, no `lzma2` (use `lzma`); re-check `DisableDirPage`/`DisableProgramGroupPage`/
   `WizardImageStretch`/`NoProgramGroupCheck2`. (Decide 5.1.10-ANSI vs 5.6.1-Unicode first per #2.)
4. Lots is **uncommitted** — commit `installer/setup.iss` + `info_after.txt` + `patch/manifest.toml`
   (HTML `Lucky☆→Lucky*` fix + active `.mink`/readme/`wallpaper.html` renames) + these docs.

### Also still open (pre-Session-9)
- **Themed calculators** (task: `WinCalcImas`/`Lucky`): `data.pak` unpacks (`sygnas_unpack.py`) to **111 PNGs +
  4 `.nut.raw`** (Squirrel source behind a light byte-framing). JP = baked-image PNGs (`btn_mode_kansan` tab,
  `conv_select_type_paper2mm` + conversion labels, `conv_btn_conv/copy`, rightmost calc buttons) + `.nut`
  textbox/font. Translate PNGs + crack the `.nut` framing + repack via `sygnas_repack.py`.

## ✅ Session 10 (2026-06-22) — agent RETIRED (session-1 SMB-exec) + FONT resolved + no-PGothic box enabled
Two owner asks: (1) the installer wizard font, (2) make SMB-exec drive the GUI so the hand-rolled
screenshot agent can retire. Both done; a 3rd front (a no-PGothic test box) opened + mostly done.

- **Agent RETIRED.** A new interactive-launch helper (i686/XP) runs any GUI program on the
  **interactive console desktop** from a session-0 SMB-exec by impersonating the active console session.
  Proven on a real XP box (real desktop capture + Inno-wizard measurement). This makes **autonomous
  GUI/UI testing** possible (no owner, no agent) — used below to measure the font wizards.

- **FONT RESOLVED — bundle MS PGothic** (no present font works). Measured every `[LangOptions]` variant
  autonomously via a window-rect helper (finds `TWizardForm`, prints GetWindowRect): PGothic-9 =
  **586×364** (faithful); Tahoma 9/10/11/12/13 = 586×420 / 586×475 / 669×530 / 752×558 / 752×614 — **none
  match** the wide-but-short 586×364 (PGothic's CJK metrics; no Latin font has that aspect ratio). **Bundle
  delivery PROVEN** via a proxy test (DejaVu Sans Mono, absent on XP): 503×392 un-bundled vs **586×420** when
  bundled + `AddFontResource(ttf)` in `[Code] InitializeSetup` → the bundled font IS available for wizard
  scaling. So bundle `msgothic.ttc` + AddFontResource it in InitializeSetup → faithful 586×364 on any XP.
  ⚠️ The app's runtime serifs (`ＭＳ Ｐゴシック` facename) ALSO need PGothic on no-lang-pack XP → the installer
  should **permanently** install msgothic.ttc ({fonts}+register), not just temp-load it for the wizard.
  → **BAKED — no font redistribution** (we ship the toolchain, not setup.exe → the BUILDER supplies their own
  MS PGothic): `tools/get_font.py` (`--ttf` / `--langpack <xp-iso|dir>` / `--windows` / `--from-system`; validates
  it's MS PGothic + decompresses the XP-CD cab) → `out/font/msgothic.ttc`; `installer/setup.iss` uses the PGothic
  `.isl` + `[Code]` (AddFontResource for the wizard + permanent `{fonts}` install for the app serifs, skipped if
  already present) + a build-time `#error` if the font's absent. **`setup.exe` compiles (47.9 MB).** Only the
  on-a-no-PGothic-XP-box 586×364 render check remains (the AddFontResource mechanism is already proven via the proxy test).

- **A second, no-PGothic XP box stood up** as a drivable test target to validate the bundled-font wizard
  render on a stock XP with no East-Asian language support. Provisioning + drivers were sorted; the only
  remaining task is the on-box PGothic-bundle render check (the AddFontResource mechanism is already proven
  via the proxy test above).

## ✅ Session 11 (2026-06-22) — themed-calculator translation (the last TL surface) + installer accel fix
The remaining untranslated user-facing surface — the iM@S / Lucky*Star themed calculators — is now EN.
Detail → [`re-notes.md`](re-notes.md) §"Session 11"; format → [`mink-format.md`](mink-format.md) §Compression.

- **Cracked the `data.pak` `.nut` LZSS** (was "deferred / different codec" since Session 1): MSB-first
  flags, set=literal; match token `len=(b0&0x0f)+2`, `dist=((b0>>4)|(b1<<4))+1` (12-bit window, overlap-
  capable). Byte-exact on all 4 `.nut`; encoder self-verifies + is tighter than SYGNAS (9873 vs 9910 B).
- **Translated `calmain.nut`** (the BPM/fps/paper converter): help text, note-length/paper labels,
  validation → pure ASCII (DrawTextA-safe). `calculator/calimas/callucky.nut` = comments-only, untouched.
- **Translated the baked button PNGs** (`tools/calc_png.py`): 電卓/単位換算 tabs, 変換/コピー, 税+/税-,
  ページ数 — erase JP by per-row gradient reconstruction, redraw EN in MS PGothic (supersampled), all size 12.
  Owner-reviewed/tuned over a screenshot preview channel.
- **Pipeline**: new build_patch **`pak` op** (`subs` re-compress `.nut` + `gen="calc_png"` retext PNGs from
  the user's OWN images at build time — no committed SYGNAS bytes). `--selftest-pak` 4/0. Verified the
  rebuilt `data.pak` changes exactly `calmain.nut` + 14 button PNGs; 100 others byte-identical.
- **Installer**: faithful parenthesized button accelerators (Back **(B)** / Next (N) / Install (I) /
  Finish **(F)**; Cancel none) matching the JP original's bundled Japanese.isl — the (F) the owner saw is
  **Finish**, not Next. `installer/luckymas-en.isl`.

**Translation surface is COMPLETE.** Remaining (recorded, non-text): the `CreateFontA` facenames (render
fine when PGothic present → the installer bundles it), MFC/VERSIONINFO boilerplate, the textless `.mink`
sprite codec. **Open**: live-on-XP render check of the translated calc (box was in NixOS this session);
the deferred wallpaper-JPG renames + `.scr` display-name pe_res; the spurious empty left-click menu (pre-existing).

### Session 11 (cont.) — the remainder: wallpaper + screensavers + header art (translation COMPLETE)
Owner-directed "finish the remainder, then test." All the deferred non-binary surface is now done:
- **Screensavers**: 4 `sys/らき☆マス：*.scr` -> ASCII (`LuckyMas - iM@S 3D.scr`, …). The Display-Properties
  picker name = the filename (the .scr's type-6 strings are the lang-1033 framework UI; only a lang-1041
  VERSIONINFO is JP = the deferred boilerplate), so the rename IS the name translation.
- **Wallpaper**: 84 `らき☆マス_<artist>_WxH.jpg` -> `LuckyMas_<romaji>_…` + the HTML `<a>/<img>` refs in
  lockstep (locale goal #2). New `rename_map` op (one 14-artist map drives renames + ref rewrite; romaji =
  the ASCII `thumb_<key>` names, paired by HTML grouping, verified 1:1). Installer `[INI]` already pins
  `Exec004 -> wallpaper.html`.
- **Header art**: the baked 壁紙の設定方法 / 壁紙一覧 / あなたのモニターサイズ images retexted. New `img_text`
  op + `calc_png.WP_HEADERS`: magenta-fill / white-border / pink-glow title (colours sampled from the JP
  original, owner-tuned bolder) on the green diamond texture — the JP run **tile-erased** (diamond period
  31, phase-aligned) so the pattern continues, EN drawn left-aligned. All owner-reviewed.

**Only deferred item left: the Launch.ini install-root path rewrite (the installer pins `{app}` via `[INI]`).**
Next: rebuild the EN `setup.exe` with all of this, then live-test on real XP.

### Session 11 (cont.) — gcal-xp: date-keyed events, fake POP3, tray, installer auto-setup
Owner-directed, after the translation: make the calendar/mail server a real, customisable, out-of-the-box thing.
- **gcalsrv.lua**: user-editable **date-keyed** `EVENTS["YYYY-MM-DD"]` / `MAIL["YYYY-MM-DD"]` tables (heavily
  documented) replace the flat ini list; `pop3_event` is now a **working fake mailbox** (STAT/LIST/UIDL/RETR/
  TOP — a real mail client can read it). gcal-xp.ini still force-overrides scenarios. Lua-5.4 tested.
- **gcalsrv.exe**: a **tray icon** (Open gcalsrv.lua / About w/ the github.com/Francesco149/**LuckyMasEN** link /
  Close), **hot-reload** on save (reload into a fresh state; keep the old one + a message box on a bad edit),
  Lua-error dialogs, and **`--install-cert`** (LocalMachine\Root, silent). `--no-tray` keeps headless SMB-exec
  runs non-blocking. Built i686/XP, smoke-tested under wine.
- **Installer**: bundles the server to `{app}\gcal-xp`, **`{commonstartup}` autostart** (tray), and a [Run]
  that trusts the cert silently then starts it. `setup.exe` recompiles + bundles it.
- **Deferred (needs RE, flagged for the XP test):** launcher-side zero-config — pre-seeding gcal's account
  (gcal.ini/gcal.dat format) so the calendar never prompts, and the `Launch.ini [Mail]` POP3 keys. Today the
  calendar works after a one-time any-login; mail is set via the launcher's Settings.

**Everything is built + committed. The remaining step is the on-XP test of the whole thing (translation +
gcal-xp + installer) — the box is in NixOS.**

## ✅ Session 12 (2026-06-23) — packaged the toolchain: one-command self-service ISO (Win + Linux)
Owner-directed pivot: stop here on XP testing (already smoke-tested) and make it **easy for an end user to
self-service an EN-patched ISO from their own disc, on Windows AND Linux with minimal friction**. Chosen
shape (asked): **per-OS native bundles** over a shared engine, freeware tools **auto-downloaded pinned +
sha256**. Detail in `CLAUDE.md` §"one-command end-user builder" + `docs/end-user-build.md`.

- **`tools/make_iso.py`** — the shared cross-platform engine. `--setup <disc setup.exe> --font auto` →
  `out/LuckyMas-EN.iso` (+`.zip`). innoextract (installed tree from setup.exe — one input file, no game
  install) → build_patch → get_font → innounp wizard art → ISCC → ISO (pycdlib else xorriso). Native
  ISCC/innounp on Windows, wine on Linux. Tool resolver: flag → PATH/known → cache → pinned download.
- **Linux**: flake `apps.iso` (`nix run .#iso`), local-checkout or remote-staged from `${self}`; gcalsrv
  self-builds via build.sh if missing. Added `xorriso`/`libarchive`/`curl` to the devshell.
- **Windows**: `installer/windows/build.bat` (+`bootstrap_python.ps1`) — private embeddable Python (dodges
  the Store-alias stub), **native ISCC, no wine**. `tools/make_windows_bundle.sh` assembles the zip from
  Linux (toolchain + prebuilt gcalsrv.exe + cache pre-seeded with the Windows tool builds → offline).
- **Validated for real**: full Linux run (byte-valid 48 MB ISO, embedded setup.exe sha == compiled) AND a
  full native build on the **Windows 10 host via WSL interop** (bootstrap Python → native ISCC 16s → valid
  48 MB ISO). Fixed: innounp overwrite-prompt hang (`-y -b`), cp1252 console crashes (ASCII/encoding-safe
  logging in make_iso + get_font), `--font auto` on native Windows (`%WINDIR%\Fonts`).

**Next (open):** a CI-built truly-zero-install Windows `.exe` (PyInstaller, no first-run Python fetch) as an
optional release artifact; otherwise the self-service builder is done + validated on both OSes. The on-XP
full-stack test (translation + gcal-xp + installer) remains the other open item from Session 11.
