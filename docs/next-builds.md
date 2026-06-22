# Next builds — calendar emulator + XP remote probe

Two builds greenlit 2026-06-21 to enable autonomous, no-physical-access work on the XP Time Machine.
Both are wslop-side to write; the one-shot boot-loop (below) is in place to test them against real XP.
**This doc is self-contained** (written before a `/clear`) — it captures the RE + design needed to execute.

## Operational context — reaching & driving the box
- The **Time Machine** runs ONE OS at a time. Default boot = NixOS courier `timemachine`
  (`ssh root@timemachine.soy`, key auth `headpats@cutestation`; reachable only while the box is in NixOS).
- **Flip into XP:** on the courier run `/root/boot-xp-once.sh` (= `grub-reboot "Windows XP (Crucial)"` +
  `systemctl reboot`). Boots XP exactly once; any XP shutdown/reboot returns to NixOS (one-shot consumed
  at the GRUB stage). Validated 2026-06-21.
- **Cold-mount the XP disk** (only while the box is in NixOS / XP cold): **ALWAYS by NTFS UUID** —
  `mount -t ntfs-3g -o ro|rw /dev/disk/by-uuid/C2DCD5A2DCD59151 /run/xp…` (the disk re-letters sda↔sdb
  across reboots — never use `sdX`). XP install root → `…/Program Files/SYGNAS/らき☆マス/{copy,launcher,calc,wallpaper}`.
- Kit master (wslop): `/mnt/c/Users/headpats/Documents/retro-machines/z97x-timemachine/retro-drivers`;
  courier mirror `/var/lib/retro-kit`; XP on-disk kit = `C:\retro-kit\` (flattened).
- Offline hive edits: `nix shell nixpkgs#hivex -c hivexregedit --merge --prefix '…' <hive> <reg>`
  (works on wslop + courier; `hivexget` is reliable on wslop, flaky on the courier — pull hives to wslop to read).

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
testing). **⚠️ corrected: run on a SEPARATE always-on LAN box, NOT the courier** — the Time Machine runs
one OS at a time, so its NixOS courier is offline while XP is booted (and XP reuses its NIC/lease, so the
courier IP would loop back to XP). Needs port 80 free.

## Build 2 — XP remote probe (screen capture + push) — cold-loop
Push files to XP + observe (screenshots) with no physical access, driven from the courier. Robust design
that reuses the proven cold-mount + boot-loop and needs **no live network agent**:
1. Courier cold-mounts XP (by UUID), writes the inputs (patched files) + a task descriptor.
2. Courier runs `boot-xp-once.sh` → reboots into XP.
3. XP **autologons** (Administrator) → a **Startup orchestrator** runs the task: launch the app, fire
   actions, **NirCmd `savescreenshot`** → `C:\probe\out\`, then `shutdown -r -t 0` → one-shot consumed →
   back to NixOS.
4. Courier returns, cold-mounts XP, reads `C:\probe\out\` → analyze.

**Pieces to stage (all offline-installable now while XP is cold):**
- **NirCmd** — NOT in the kit; fetch from nircmd.com (Playwright if the DL is gated) → `C:\probe\nircmd.exe`.
- **Autologon** — SOFTWARE hive `…\Microsoft\Windows NT\CurrentVersion\Winlogon`: `AutoAdminLogon=1`,
  `DefaultUserName=Administrator`, `DefaultPassword=…`. ✅ **Resolved 2026-06-21: Administrator password is
  BLANK** (offline `samdump2` → NT hash `31d6…089c0`; owner-confirmed) → leave `DefaultPassword` empty.
- **Startup orchestrator** — a batch in `…\Documents and Settings\All Users\Start Menu\Programs\Startup\`
  that, **only when a flag file exists** (so normal boots aren't hijacked), runs `C:\probe\task.cmd` (dropped
  by the courier) + screenshots + reboots.
- **Courier orchestrator** — a script doing steps 1–4 (mount/write/arm/reboot; on return mount/read).

**Optional later upgrade (live agent):** portable sshd (Bitvise WinSSHD) installed on first boot via the
orchestrator → live SFTP+exec on running XP (no reboot per change). Defer until the cold-loop works.

## State at this `/clear` (2026-06-21)
- **LuckyMas:** 22-char EN launcher translation **deployed** to XP (originals backed up
  `courier:/root/luckymas-launcher-orig.20260621-202727`; owner confirmed names + one speech line render in
  English). Formats MINK/ACZ/PACKDATA cracked; `tools/` = `sygnas_unpack.py` / `sygnas_repack.py` /
  `build_launcher_en.py`; `patch/launcher/*.ini`. Calc `.nut` + `.mink` sprite codecs deferred (don't gate TL).
- **Shutdown SOLVED:** Creative Audigy autostarts (`CTSysVol` + `Module Loader/DLLML`) parked → instant
  (revert: re-merge from `Run-LMparked`, or restore `courier:/root/xp-SOFTWARE.bak.20260621-210113`).
  `verbosestatus=1` + per-user app-kill timeouts (2000/1000/AutoEndTasks=1) also set.
- **One-shot boot-loop done + validated** (`courier:/root/boot-xp-once.sh`).
- **SMBus INF deployed but the boot "new hardware" wizard still appears** — needs a manual Device-Manager
  install from `C:\retro-kit\chipset-inf\`, or it's a *different* undriven device (iGPU/xHCI → BIOS-disable). Deferred.
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
  client): schedule/none/error, mail check/none/error/refuse. ⚠️ **runs on a SEPARATE always-on LAN box,
  not the courier** (the courier IS XP while XP runs); needs port 80 free + on the `10.0.10.x` LAN.
- **Build 2 — XP remote probe** → `retro-hardware/projects/xp-remote-probe/` (`courier/xp-probe.sh` +
  `xp/*.cmd|.reg` + README). Deployed to `courier:/root/xp-remote-probe/`; NirCmd staged to the kit
  (`xp/probe/nircmd.exe`, 32-bit verified). **Validated on the real cold disk (no reboot):** UUID mount
  guard, case-insensitive resolver, install, status, `hosts on|off`, `autologon on|off` (readback via
  `hivexregedit --export`; `hivexget` isn't exposed by `nix shell nixpkgs#hivex`), and `check-admin`.
  Disk left clean (autologon off, no redirect, no flag).

**One open step:** the first full cold-loop `arm → reboot → collect` (reboots the box into XP). Gated on
an owner go-ahead. Recommended first run **owner-supervised** (skip autologon, log in by hand once);
enable autologon for hands-off runs after the loop is proven. Runbook → the probe README.

### Hosting + the XP-local direction (2026-06-21)
The emulator can't run on the Time Machine courier (it *is* XP during the run), so it's wired onto the
**`code` box behind its Caddy**: `nix-lab/hosts/code/gcal-emu.nix` (a localhost service on
`lab.ports.gcal-emu`=8091) + a plain-HTTP `http://www.google.com` Caddy vhost → it. XP's hosts redirect
points `www.google.com → 10.0.10.53` (`code`). Committed + eval/Caddyfile-validated; **needs `deploy .#code`
to go live.** Calendar-only (POP3 can't be Caddy-fronted → mail deferred).

**Build 3 (future, owner-requested):** a **user-friendly XP-local** emulator the end user runs on their
own XP box (`hosts www.google.com → 127.0.0.1`) to enjoy the mascots' calendar/mail with no Google account
— so it must be **native (no Python on XP)**: the protocol is tiny (HTTP/1.0 + POP3) → a small Win32 C
build (mingw-w64, XP subsystem) is the target, written with confidence from the confirmed wire format +
whatever the request logger captures on the first real run.

## ✅ Session 2 (2026-06-22) — live-tested; one open piece (HTTPS ClientLogin)
- **Live-control infra built + proven** (the "optional live agent", done — details in the probe README):
  a tiny **curl agent `xphttpd`** on XP (runs as Administrator in the interactive session → real
  screenshots) + **`netexec`/SMB** for clean deploys. The Bitvise-sshd idea was a dead end (deep config
  rabbit hole) → replaced. This is what made the live recon possible, **no cold-loop reboots**.
- **gcal-emu reachable from XP** (`code` deployed; hosts-redirect verified; gcal.exe launches + prompts
  for an account; the **HTTP feeds are ready**).
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
- **The code-hosting route kept fighting infra:** `code`'s Caddy **wildcard-binds `*:80`/`*:443`**, so even
  a secondary IP (`10.0.10.54`) can't take `:443`. On XP, `hosts → 127.0.0.1` and our server owns
  `127.0.0.1:{80,443,110}` with nothing else there → the whole hosting apparatus evaporates.
- It's the actual product (no Google account) and kills the separate-always-on-box requirement + the
  POP3-can't-be-Caddy-fronted limitation in one move.

**De-risked this session — the XP-era handshake works:** a TLS1.0 + RSA-kx **AES128-CBC-SHA** client (XP
SP3's exact capability) against our **SHA-1/RSA-2048 self-signed `www.google.com`** cert completes and
returns `Auth=` (local OpenSSL proof; the gcal-emu `--https` listener + `certs/` + `make-xp-cert.sh`).
So XP's WinINet will handshake our cert; the native Schannel server reproduces the same.

**Target architecture — one self-contained Win32 EXE (i686, XP subsystem):**
- plain sockets for **HTTP feeds (:80)** + **POP3 (:110)** — trivial C (`xphttpd` proves the socket
  scaffolding; the response logic ports straight from `gcal_emu.py`, kept as the protocol oracle).
- **Schannel** for **HTTPS `/accounts/ClientLogin` (:443)** — the one fiddly piece
  (`AcquireCredentialsHandle` → `AcceptSecurityContext` token loop → `Encrypt/DecryptMessage`); only
  debuggable on XP via the live agent (no local loop / debugger). Raw Schannel honors "use XP's own
  ciphers"; **fallback** = statically link mbedTLS (portable/testable on Linux, bigger EXE) only if
  Schannel server-side fights us.
- cert in-process: bundle the cert+key as `.pfx` → **`PFXImportCertStore`** gives Schannel its server
  credential (no system store needed); **`CertAddEncodedCertificateToStore(ROOT,…)`** installs the public
  cert so WinINet trusts it. **Install into Root by default** (WinINet won't trust self-signed otherwise;
  harmless if gcal.exe ignored cert errors → no separate trust-probe needed).
- first-run/installer: `hosts: www.google.com → 127.0.0.1`, drop+autostart the EXE (Startup, like xphttpd).

**Next steps:** (1) make the `.pfx`; (2) plain-socket HTTP/POP3 core (port `gcal_emu.py` responses to C);
(3) Schannel ClientLogin handshake + in-proc cert install; (4) i686-mingw build (cached on `code` via
`nix … pkgsCross.mingw32.buildPackages.gcc`), deploy via netexec, drive gcal.exe via the agent, capture
the Serif bubbles. The `code`-hosted Python path is **retired for the deliverable, kept as the oracle**.

## ✅ Session 4 (2026-06-22) — native server BUILT + Schannel PROVEN on real XP
Steps 1–3 + the build of step 4 are **done**: `tools/gcal-xp/gcalsrv.c` (one self-contained 80 KB i686 EXE)
serves HTTP feeds :80 + POP3 :110 (Winsock) + **HTTPS ClientLogin :443 (Schannel)**, cert embedded as an
XP-legacy PKCS#12 (`cert_pfx.h`). Cross-built via `build.sh` (mingw + nix), deployed + driven on
**10.0.10.113 via SMB-exec (netexec)**. **Validated live:** a real XP WinINet client (`MSXML2.XMLHTTP` =
gcal.exe's stack, `test/clientlogin.vbs`) completes the **Schannel handshake**, **trusts** the self-signed
cert, and gets `Auth=` from ClientLogin (`STATUS=200`); HTTP feeds + POP3 also verified. Full build log,
the five bugs fixed (legacy-PKCS12, mcfgthread/XP-safety, protected-root modal, handshake-crash, SYSTEM
keyset), and the SMB-exec-not-the-agent operating rule → [`re-notes.md`](re-notes.md) §"Session 4".

**Remaining:** (A) **migrate the request logic to embedded Lua** (owner-directed; C keeps sockets+Schannel+
POP3, Lua gets routing/Atom/config — the `http_handle()` seam is already isolated). (B) the final end-to-end:
drive the real `gcal.exe`/launcher → fire the `SerifCallender*`/`SerifMail*` bubbles (server side done; this
is launcher-render validation, needs GUI driving). (C) unattended cert install (certutil/registry, no modal)
+ first-run installer (hosts + Startup).
