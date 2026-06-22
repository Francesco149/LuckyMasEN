# XP ops cheatsheet — agent-LESS (SMB-only) mode

When the **xphttpd agent (`:8099`) is NOT running** but SMB is, this is how to deploy + drive the
Time Machine from wslop using only **netexec** (exec) + **smbclient** (files). `tools/deploy-xp.sh`
is the *agent-centric* recipe (its `probe`/`server`/`launch`/`shot`/`clientlogin` call the agent);
this file is the fallback for everything that doesn't need the GUI. Validated 2026-06-22 (Session 8).

## Box facts
- **10.0.10.113** (DHCP floats `.113`/`.114`/`.115`), host `TIMEMACHINE-XP`, **SMBv1/NT1 only**.
- **Administrator / BLANK password.** `(Pwn3d!)` on connect = auth OK.
- wslop reaches it **directly** on the `10.0.10.x` LAN — no need to hop through `code`.
- GUI / screenshots still need the **agent or the owner** (smbexec is session-0-blind; the mascot is a
  layered window). Loop the owner in for visual checks — that's the fast path.

## The two channels
```sh
# EXEC (netexec / wmiexec):
nix run nixpkgs#netexec -- smb 10.0.10.113 -u Administrator -p '' -x '<cmd>'

# FILES (smbclient — force NT1 or the dialect negotiation times out):
nix shell nixpkgs#samba -c smbclient '//10.0.10.113/C$' -U 'Administrator%' \
  -m NT1 --option='client min protocol=NT1' -c '<smb-commands>'
```
smbclient tips: `prompt OFF` before `mput`; `lcd <localdir>` to set the local side; **always give `get`
a local name** — `get "\path\file" name` — else you get a file literally named `\path\file`. Remote
paths use backslashes; quote ones with spaces. The `Can't load /etc/samba/smb.conf` warning is harmless.

## Getting command OUTPUT back reliably (the #1 gotcha)
wmiexec's output retrieval is **flaky for inline complex commands** (`(...)`, `&`-chains, redirects →
"Could not retrieve output file" or an empty/stale read). **A pushed `.bat` is reliable**: small stdout
comes straight back, and a redirect *inside* the `.bat` to a file is rock-solid.

**Rule:** when you need output, write a `.bat` that redirects to `C:\gcal-xp\X.out`, run the `.bat` via
netexec, then `smbclient get` the `.out`. Pure file inspection (`ls`/`get` of existing files) is always
reliable via smbclient — prefer it over `tasklist`/`type` through exec when you only need filesystem facts.

## Launching a PERSISTENT process without the agent (the big lesson)
- `start "t" "C:\..\x.exe"` via wmiexec → **FAILS silently** (non-interactive session-0 window station;
  the process never spawns, no log appears).
- `schtasks /create … /f` → **FAILS on XP** (`/f` is Vista+: "Invalid Argument/Option - '/f'").
- ✅ **Direct exec works:** `netexec … -x 'C:\gcal-xp\gcalsrv.exe'`. gcalsrv is **GUI-subsystem**
  (`-mwindows`), so `cmd /c` returns immediately and the process persists detached. This is the launch.
  (Any `-mwindows` server EXE launches this way; a *console* EXE would make `cmd /c` block — use a `.bat`
  with `start` only from the interactive agent, never from wmiexec.)

## gcalsrv full lifecycle (agent-less)
```sh
# 1. Rebuild (keeps the CN=localhost cert_pfx.h; regens lua; asserts XP-only imports)
bash tools/gcal-xp/build.sh

# 2. Push the .bat helpers once (contents below), then kill+clean, push fresh build, start, verify.
#    helper .bats live in C:\gcal-xp\ on the box (gkill/gstart-unused/clrun/probe/gtask).
SMB='//10.0.10.113/C$'; U='Administrator%'; NT="-m NT1 --option=client min protocol=NT1"

# kill any running gcalsrv + delete stale exe + log (one wmiexec call, & = sequential)
nix run nixpkgs#netexec -- smb 10.0.10.113 -u Administrator -p '' -x 'C:\gcal-xp\gkill.bat'

# push fresh exe + cert + headless test client
nix shell nixpkgs#samba -c smbclient "$SMB" -U "$U" $NT -c \
  'prompt OFF; cd \gcal-xp; lcd tools/gcal-xp; mput gcalsrv.exe; lcd tools/gcal-emu/certs; mput xp-google.der; lcd tools/gcal-xp/test; mput clientlogin.vbs'

# start (direct exec — NOT start/schtasks)
nix run nixpkgs#netexec -- smb 10.0.10.113 -u Administrator -p '' -x 'C:\gcal-xp\gcalsrv.exe'

# verify server: fetch the log
nix shell nixpkgs#samba -c smbclient "$SMB" -U "$U" $NT -c 'lcd /tmp; get "\gcal-xp\gcalsrv.log" gcalsrv.log'
#   expect: cert CN=localhost · gcalsrv ready (3 listeners) · cert: install -> LocalMachine\Root: ok

# prove the client TLS path: run clientlogin.vbs -> cl.out, fetch it
nix run nixpkgs#netexec -- smb 10.0.10.113 -u Administrator -p '' -x 'C:\gcal-xp\clrun.bat'
nix shell nixpkgs#samba -c smbclient "$SMB" -U "$U" $NT -c 'lcd /tmp; get "\gcal-xp\cl.out" cl.out'
#   expect: URL=https://localhost/accounts/ClientLogin · STATUS=200 OK · Auth=EMU_TEST_TOKEN
```

### The .bat helpers (write CRLF; doubled backslashes so printf emits single ones)
```sh
printf 'taskkill /f /im gcalsrv.exe & del /f /q C:\\gcal-xp\\gcalsrv.exe & del /f /q C:\\gcal-xp\\gcalsrv.log & echo KILLED\r\n' > gkill.bat
printf 'cscript //nologo "C:\\gcal-xp\\clientlogin.vbs" > "C:\\gcal-xp\\cl.out" 2>&1\r\n' > clrun.bat
# probe.bat: tasklist + log presence (use a .bat, not inline, for output)
printf 'tasklist /fi "imagename eq gcalsrv.exe" > C:\\gcal-xp\\probe.out 2>&1\r\ndir C:\\gcal-xp\\gcalsrv.log >> C:\\gcal-xp\\probe.out 2>&1\r\n' > probe.bat
```

## Cert install (CN=localhost)
- gcalsrv installs the public cert into **both** `CurrentUser\Root` *and* `LocalMachine\Root` on a
  **background thread** (so the protected-root modal can't block serving). Run **as SYSTEM via wmiexec →
  both install SILENTLY** (`…Root: ok`, no modal). `LocalMachine\Root` = trusted by **all** users' WinINet.
  Launched *interactively*, a protected-root modal can pop → owner clicks **Yes** once (owner did, 2026-06-22).
- Cert = `CN=localhost` + SAN(`localhost,127.0.0.1,www.google.com,google.com,*.google.com`). The deliverable
  connects to **`https://localhost`** (gcalcore.dll/gcal.exe binpatched), and `hosts` has **no** google
  redirect (just `127.0.0.1 localhost`). The CN in the log is read live (`CertGetNameStringA`) — trust it.
- The XP log's `PFX user-keyset import failed 0x8009000b; retrying machine keyset` is the benign,
  handled fallback (NTE_BAD_KEYSET) — machine keyset then succeeds.

## Gotcha: gcalsrv.exe / gcalsrv_lua.h are GITIGNORED build artifacts
The committed *source* (`gcalsrv.c`/`gcalsrv.lua`) + `cert_pfx.h` are the truth; the EXE on disk (or on
XP) can be **stale**. Always `build.sh` before trusting a deployed binary. (Session 8 found XP running an
old `CN=www.google.com` build while the source/cert were already `CN=localhost`.)

## hosts
Current state = `127.0.0.1 localhost` only (the localhost deliverable). To toggle the legacy
`www.google.com → 127.0.0.1` redirect use `tools/deploy-xp.sh hosts-off|hosts-on` (pull/filter/push;
backup kept as `hosts.lmbak`). Editing hosts via chained `cmd` redirection is unreliable — always
pull/filter/push the file.

## Boot loop reminder
XP booted ⇒ the NixOS courier `timemachine` is OFFLINE (one OS at a time). To get NixOS-side
(cold-mount/hive edits): reboot XP → it returns to NixOS one-shot; re-arm with
`ssh root@timemachine.soy /root/boot-xp-once.sh`.
