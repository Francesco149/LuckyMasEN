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

**Protocol the launcher speaks** (RE'd from `gcalcore.dll` / `gcal.exe` / `Launch.exe` — all **WinINet over
plain `http://` to `www.google.com`**, 2007 ClientLogin + GData Atom; **NO HTTPS** → a hosts redirect +
a plain HTTP server suffice, no cert):
- `POST /accounts/ClientLogin`  body `Email=%s&Passwd=%s&service=cl&source=sygnas-gcal-0.1`
  → respond `SID=x\nLSID=x\nAuth=<token>\n` (it only reads `Auth=`).
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
whatever the request logger captures on the first real run. Pair with the probe's **optional live agent**
(portable sshd on XP) to read logs + iterate **without** the cold-loop reboot.
