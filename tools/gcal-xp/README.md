# gcal-xp — native XP-local fake-Google server for the らき☆マス launcher

`gcalsrv.exe` is one self-contained Win32 EXE the end-user runs on **their own Windows XP box** so the
launcher's **calendar** (`gcal.exe`/`gcalcore.dll`) and **mail** (`Launch.exe`) mascots work with **no
Google account**. XP's `hosts` points `www.google.com → 127.0.0.1` and this server answers as Google:

| port | proto | what |
|---|---|---|
| `:80`  | HTTP/1.0 (Winsock) | GData feeds — allcalendars list + event feed + add-event deep-link |
| `:443` | HTTPS (**Schannel**) | `/accounts/ClientLogin` → `Auth=…` |
| `:110` | POP3 (Winsock) | `USER`/`PASS`/`STAT` → mail count |

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
gcalsrv.exe                 REM serve :80/:443/:110, install cert into Root (background)
gcalsrv.exe --no-cert       REM don't touch the cert stores (cert already trusted)
gcalsrv.exe --install       REM also: add the hosts redirect + copy self to Startup, then serve
gcalsrv.exe --no-tls        REM HTTP + POP3 only (skip Schannel)
gcalsrv.exe --http 8080 --https 8443 --pop 1110   REM alt ports (testing)
```

Logs every request + handshake step to `gcalsrv.log` (next to the EXE). Reads `gcal-xp.ini` (next to the EXE,
re-read per request) for the scenario.

## Config (`gcal-xp.ini`, `key=value`, optional)

| key | default | meaning |
|---|---|---|
| `calendar` | `schedule` | `schedule` (events) · `none` (empty) · `error` (403) |
| `mail` | `check` | `check` (n>0) · `none` (0) · `error` (`-ERR`) · `refuse` (drop) |
| `events` | `Dentist;Lunch with Konata;Buy doujinshi` | `;`-separated event titles |
| `mailcount` | `3` | message count for `mail=check` |
| `calname` / `account` / `tzoffset` | `Test Calendar` / `test@example.com` / `+09:00` | feed metadata |

Bubble ↔ scenario mapping: same as `../gcal-emu/README.md`. (Future: a real local-calendar backend.)

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

- ✅ **Lua request logic** (`gcalsrv.lua`) — done + validated on real XP; responses byte-identical to the
  C version. Next: a real local-calendar backend (read events from a local file/ICS) — now a script edit.
- First-run installer: silent cert install (certutil/registry, no modal) + `hosts` redirect + Startup autostart.
- End-to-end: drive the real `gcal.exe`/launcher → capture the `SerifCallender*`/`SerifMail*` bubbles.
