# CLAUDE.md — LuckyMasterEN orientation

English fan-translation **patch + tooling** for SYGNAS 「らき☆マス」 (*Lucky☆Mas*, 2007 doujin
desktop-accessory pack) + an RE log for its in-house **MinkIt** mascot engine, and a **native
XP-local fake-Google server** so the launcher's calendar/mail mascots work with no Google account.

Read first: `README.md`, `docs/re-notes.md` (RE log), `docs/next-builds.md` (the build plan +
session log), `docs/mink-format.md` (container specs). Upstream scope:
`../retro-hardware/projects/minkit-en-patch/README.md`.

## Sibling repos
- **`../retro-hardware`** — the Windows XP "Time Machine" hardware build + XP infra. Key:
  `HANDOFF.md` (fleet + access), `projects/xp-remote-probe/` (the live agent + cold-loop used to
  drive XP), `builds/` (the courier NixOS configs).
- **`../nix-lab`** — the home-lab NixOS flake. Hosts: `code` (always-on orchestrator — our deploy +
  cross-build box), `cold`, `lame`, `mail`, `relay`, `wslop` (this dev box). The retired
  Python-hosting scaffolding lives at `hosts/code/gcal-emu.nix` (kept; pivoted away from it).

## Hard rule
Never commit or redistribute any SYGNAS original file. `originals/` is gitignored. We ship only a
delta + tooling that applies to the user's own disc copy. The `certs/` self-signed `www.google.com`
fixture is NOT a SYGNAS file and NOT a secret (a LAN-isolated fake-Google fixture) → committed on
purpose so the served cert == the cert installed in XP's Root, byte-for-byte.

## The Time Machine (the XP target)
- i7-4790K / Z97X-UD3H. Runs **ONE OS at a time**: NixOS courier `timemachine` (default boot) **or**
  Windows XP **or** Win7. MAC `74:d4:35:ea:6d:f2`; DHCP IP floats (seen `.113`/`.114`/`.115`).
- XP disk NTFS UUID **`C2DCD5A2DCD59151`**. Cold-mount **by UUID only** (the disk re-letters
  sda↔sdb across boots): `mount -t ntfs-3g -o ro|rw /dev/disk/by-uuid/C2DCD5A2DCD59151 /mnt/…`
  (only while the box is in NixOS / XP cold; guard on `ntoskrnl.exe` presence before writing).
- App install root on XP: `C:\Program Files\SYGNAS\らき☆マス\{copy,launcher,calc,wallpaper}`.
  Calendar client = `…\launcher\{gcal.exe,gcalcore.dll}`; mail = `…\launcher\Launch.exe`.

## Reaching + driving the box
**When XP is booted, the courier `timemachine` is OFFLINE** (one OS at a time; XP reuses the NIC
lease). Reach XP directly:
- **xphttpd agent** (runs as Administrator in the interactive session → real screenshots, launches
  GUI apps the owner sees): `http://<xp-ip>:8099/` — `GET /ping`; `GET /run?k=rmprobe2026&c=<urlcmd>`
  (cmd.exe, returns stdout+stderr, 30 s cap); `GET /reboot?k=rmprobe2026` (→ back to NixOS).
  Source: `../retro-hardware/projects/xp-remote-probe/xp/xphttpd.c`.
- **netexec/SMB from `code`** (clean deploys + agent rescue; blind to the GUI — session 0):
  `ssh root@code.soy` then `nix run nixpkgs#netexec -- smb <xp-ip> -u Administrator -p '' -x '<cmd>'`
  (`--put-file` / `--get-file` to move files). Admin password is **BLANK**.

**When NixOS is booted:** `ssh root@timemachine.soy` (key auth `headpats@cutestation`).

## Boot loop (NixOS ⇄ XP) — recoverable
- Default boot = NixOS. **Flip into XP:** on the courier run `/root/boot-xp-once.sh`
  (`grub-reboot "Windows XP (Crucial)"` + `systemctl reboot`). Boots XP **exactly once**; any XP
  shutdown/reboot returns to NixOS (one-shot consumed at the GRUB stage).
- **Re-arming is always available:** if XP reboots back to NixOS (or you call the agent's `/reboot`),
  the courier comes online → `ssh root@timemachine.soy /root/boot-xp-once.sh` flips it back to XP.
  So rebooting XP is **not** a lockout — it just costs one NixOS round-trip. Use a reboot whenever you
  need NixOS-side work (cold-mount, hive edits) or a clean XP restart.
- Offline hive edits (box in NixOS / XP cold): `nix shell nixpkgs#hivex -c hivexregedit --merge …`.

## Building XP binaries (i686, XP subsystem)
Cross-compile with mingw-w64 via nix (works locally on wslop; also cached on `code`):
```sh
nix shell nixpkgs#pkgsCross.mingw32.buildPackages.gcc --command \
  i686-w64-mingw32-gcc src.c -o out.exe -lws2_32 -O2 -s -mwindows \
  -D_WIN32_WINNT=0x0501 -Wl,--major-subsystem-version=5,--minor-subsystem-version=1
```
The `--*-subsystem-version=5.1` + `_WIN32_WINNT=0x0501` make the PE load on XP. Schannel/CryptoAPI
builds add `-lsecur32 -lcrypt32`.

## The gcal-xp native server (`tools/gcal-xp/`) — the current build
One self-contained Win32 EXE the user runs on their own XP box (`hosts: www.google.com → 127.0.0.1`)
so the mascots' calendar/mail work with no Google account:
- **HTTP feeds `:80`** (allcalendars list + event feed + add-event deep-link) + **POP3 `:110`** —
  plain Winsock.
- **HTTPS `/accounts/ClientLogin` `:443`** — **Schannel** (server + client are the same 2007 stack →
  period-accurate TLS by construction; no modern-TLS coercion). Cert = self-signed `www.google.com`
  (RSA-2048/SHA-1) embedded as a PFX (`cert_pfx.h`), installed into XP's **Root** in-process so
  WinINet trusts it.
- **`tools/gcal-emu/gcal_emu.py`** is the protocol **oracle** (Python; retired as a deployed host,
  kept as the reference for the exact responses). Wire format + bubble↔scenario table:
  `docs/next-builds.md` §"Build 1"/§"Session 3".

## Conventions
- Persist cross-session **orientation in this CLAUDE.md**; the running RE/build narrative in
  `docs/re-notes.md` + `docs/next-builds.md`. Windows-bound `.txt`/`.reg`/`.cmd` files = CRLF.
- `nix develop` drops into the RE/TL shell (ghidra, rizin, wrestool, wine, qemu, python+lief…).
