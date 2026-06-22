# gcal-xp — native XP-local fake-Google server for the らき☆マス launcher

`gcalsrv.exe` is one self-contained Win32 EXE the end-user runs on **their own Windows XP box** so the
launcher's **calendar** (`gcal.exe`/`gcalcore.dll`) and **mail** (`Launch.exe`) mascots work with **no
Google account**. XP's `hosts` points `www.google.com → 127.0.0.1` and this server answers as Google:

| port | proto | what |
|---|---|---|
| `:80`  | HTTP/1.0 (Winsock) | GData feeds — allcalendars list + event feed + add-event deep-link |
| `:443` | HTTPS (**Schannel**) | `/accounts/ClientLogin` → `Auth=…` |
| `:110` | POP3 (Winsock) | a working fake mailbox — `USER`/`PASS`/`STAT`/`LIST`/`UIDL`/`RETR`/`TOP` |

Why native (vs. the old `code`-hosted Python): on XP the server speaks **Schannel** and the client is
**WinINet** — the *same* 2007 stack, so the TLS handshake is **period-accurate by construction** (no modern-TLS
coercion, no separate always-on box). The Python `../gcal-emu/gcal_emu.py` is kept as the protocol **oracle**.

**Architecture:** C owns the transport — Winsock sockets, the Schannel TLS handshake/encrypt/decrypt, POP3
line framing, the cert, and the HTTP/1.0 status-line/headers. The **request logic lives in Lua**
(`gcalsrv.lua`): routing, the Atom feed builders, the ClientLogin/POP3 responses, and the `gcal-xp.ini`
scenario. Lua 5.4 is statically embedded; the script is carried inside the EXE but an external
`<exedir>\gcalsrv.lua` overrides it — so a real local-calendar backend is a script edit, no rebuild. The C↔Lua
boundary is two calls: `http_handle(method,path,query,body)→status,ctype,body` and `pop3_event(verb,arg)→reply,action`.

**Status:** ✅ built + **validated on real XP SP3** (2026-06-22). A real WinINet client completes the
Schannel handshake, trusts the embedded cert, and gets `Auth=` from ClientLogin; HTTP feeds + POP3 verified.
See `../../docs/re-notes.md` §"Session 4".

## Build

```sh
./build.sh          # i686-w64-mingw32 via nix → gcalsrv.exe (XP subsystem 5.1, static)
```

It cross-compiles with mingw-w64 (fetched via nix), builds `liblua.a` from the nix-pinned Lua 5.4 source
(cached in `.luabuild/`), statically links it + the mcf threads runtime (dead-stripped — we use native
`CreateThread`) so the EXE imports **only XP system DLLs**, and targets subsystem 5.1 + fixed base (`-no-pie`).
`embed-pfx.sh` regenerates `cert_pfx.h` (the embedded cert); `embed-lua.sh` regenerates `gcalsrv_lua.h` (the
embedded default script) from `gcalsrv.lua`. Edit `gcalsrv.lua` and rebuild (or just redeploy it as an external
override) to change the logic.

## The cert

Self-signed `www.google.com` leaf (RSA-2048/SHA-1, 20y), shared with `gcal-emu` (`../gcal-emu/certs/`), carried
inside the EXE as an **XP-legacy PKCS#12** (pbeWithSHA1And3-KeyTripleDES-CBC + SHA-1 MAC — XP's
`PFXImportCertStore` can't parse OpenSSL 3.x's PBES2/AES default). At startup the server imports it for
Schannel's server credential (user keyset, falling back to **machine keyset** under SYSTEM) and installs the
public cert into XP's **Root** so WinINet trusts the TLS endpoint.

⚠️ **The in-process Root install pops XP's protected-root confirmation modal** and is done in a background
thread (so it never blocks serving). For an **unattended/silent** install, import the cert out-of-band instead
and run with `--no-cert`:

```bat
certutil -addstore -f Root C:\gcal-xp\xp-google.cer        REM LocalMachine\Root (admin)
```

(or write the registry blob directly). *TODO: bake a silent cert install into the first-run installer.*

## Run / flags

```bat
gcalsrv.exe                 REM serve :80/:443/:110 + a TRAY ICON, install cert into Root (background)
gcalsrv.exe --no-cert       REM don't touch the cert stores (cert already trusted)
gcalsrv.exe --install-cert  REM import the cert into LocalMachine\Root (silent, admin) and exit
gcalsrv.exe --no-tray       REM headless: no tray/dialogs (for SMB-exec as LocalSystem), serve forever
gcalsrv.exe --install       REM also: add the hosts redirect + copy self to Startup, then serve
gcalsrv.exe --no-tls        REM HTTP + POP3 only (skip Schannel)
gcalsrv.exe --http 8080 --https 8443 --pop 1110   REM alt ports (testing)
```

**Tray icon** (interactive runs): right-click → **Open gcalsrv.lua** (drops the embedded default if there's
no external copy, then opens it in your editor), **About** (what it does + the repo link), **Close**. The
server **hot-reloads** `gcalsrv.lua` when you save it (a broken edit keeps the previous script running and
pops the Lua error in a message box). Logs every request to `gcalsrv.log` (next to the EXE).

## Customise — events & mail (edit `gcalsrv.lua`)

The mascot's calendar/mail content lives in `gcalsrv.lua` (re-read on save). Edit the two tables at the top:

```lua
local EVENTS = { ["2026-06-23"] = { { title = "Dentist", at = "10:00", where = "Akihabara" }, "Buy doujinshi" } }
local MAIL   = { ["2026-06-23"] = { { from = "konata@...", subject = "new figs!!", body = "..." } } }
```

A date with events → `SerifCallenderSchedule` (titles); an absent/empty date → `SerifCallenderNone`. Mail
count > 0 → `SerifMailCheck`, else `SerifMailNone`; the POP3 side is a **working fake mailbox** (STAT/LIST/
UIDL/**RETR**/TOP), so a real mail client can log in and read the messages too. `TODAY`/identity knobs are up top.

`gcal-xp.ini` (optional, next to the EXE) still **force-overrides** a scenario for testing: `calendar =
none|error`, `mail = none|error|refuse`, `today = YYYY-MM-DD`, `events = A;B;C`, `mailcount = N`,
`account`/`calname`/`tzoffset`.

## Out of the box (via the LuckyMasEN installer)

The English installer bundles `gcalsrv.exe`+`gcalsrv.lua` to `{app}\gcal-xp`, **trusts the cert** silently
(`--install-cert` → LocalMachine\Root, as admin, no modal), **autostarts** the server (tray) for every user
(`{commonstartup}`), and starts it immediately. The launcher's calendar/mail already point at `localhost`
(host→localhost binpatch), so they reach it. *(Launcher-side zero-config — pre-seeding gcal's account so the
calendar never prompts, and the Launch.ini `[Mail]` POP3 keys — still needs RE; today the calendar works
after a one-time any-login and mail is configured via the launcher's Settings.)*

## Deploy / drive on XP (this LAN)

⚠️ The **xphttpd agent is single-threaded** — a forever-running child wedges it. Drive everything through
**SMB-exec**, reserve the agent for **screenshots**:

```sh
# from `code` (LAN box with netexec); XP at its DHCP IP (e.g. 10.0.10.113), admin pw blank
NXC="nix run nixpkgs#netexec -- smb <xp> -u Administrator -p ''"
$NXC --put-file gcalsrv.exe '\gcal-xp\gcalsrv.exe'
$NXC -x 'C:\gcal-xp\gcalsrv.exe --no-cert'     # headless; runs as SYSTEM (machine keyset)
$NXC --get-file '\gcal-xp\gcalsrv.log' ./gcalsrv.log   # read the log back
```

`test/clientlogin.vbs` (push + `cscript //nologo`) is a headless WinINet probe of the whole ClientLogin/TLS/
cert-trust path — the proof used in Session 4.

## Roadmap

- ✅ **Lua request logic** (`gcalsrv.lua`) — validated on real XP; byte-identical to the C version.
- ✅ **Date-keyed events + a working fake POP3 mailbox** (EVENTS/MAIL tables; RETR-able) — the "real local
  backend", as a documented script edit.
- ✅ **Tray UI + hot-reload + Lua-error dialogs**; **silent cert install** (`--install-cert`).
- ✅ **Installer auto-setup** — bundle + `{commonstartup}` autostart + silent cert trust.
- End-to-end: drive the real `gcal.exe`/launcher → capture the `SerifCallender*`/`SerifMail*` bubbles
  (Schedule/None done in Session 4). **Launcher-side zero-config** (pre-seed gcal's account; the
  `Launch.ini [Mail]` POP3 keys) — needs RE.
