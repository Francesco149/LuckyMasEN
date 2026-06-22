# MinkIt / Lucky☆Mas — RE log

Running reverse-engineering notes. Scope + constraints: upstream
`retro-hardware/projects/minkit-en-patch/README.md`. Format specs: [`mink-format.md`](mink-format.md).

---

## 2026-06-21 — Session 1: extraction + first recon

### Acquisition (no XP-disk pull needed)
Local kit ISO on wslop → `setup.exe` = **Inno Setup 5.1.10** (app "らき☆マス デスクトップアクセサリ
Ver1.00") → `innoextract --codepage 932` → full installed tree in `originals/installed/` (164 files).
Cleaner + pristine vs the scope doc's "rsync from the XP install".

### The app tree (corrected layout)
Install root = **`C:\Program Files\SYGNAS\らき☆マス\`** (the scope doc's `らき―copy` was a misread).
- `copy/` — **MinkIt engine**: `MinkIt.exe` + `MinkIt.dll` + 10 `.mink` (= the "コピーアニメーション").
- `launcher/` — **23-char app launcher**: `Launch.exe` + `Launch.ini`(`.org`) + 23 `.Xvi` + `gcal.exe`/`gcalcore.dll` + `gdiplus.dll`.
- `calc/` — **calculators**: `WinCalc.exe` (full) + `WinCalcImas.exe` + `WinCalcLucky.exe` (100 KB thin themes) + `data.pak` + `gmp.dll` + `mpfr.dll`.
- `wallpaper/` — HTML/CSS/JS picker (`壁紙えらび.html` + jQuery) + JPGs.
- `sys/` — the **4 screensavers** `.scr` (JP-named).

### Build / compiler (corrected)
All four PE32 are native **Win32 C/C++, MSVC 2005 ("Linker 08.00"), cdecl, unstripped, NOT packed.**
→ explains the scope doc's "VB6/Delphi/.NET signatures empty; maybe packed" — it's plain C/C++.
Ghidra-friendly.

### Per-binary (imports + resources)
| binary | role | key imports | UI text (resources, lang 1041) |
|---|---|---|---|
| `MinkIt.exe` 73 KB | front-end; loads own `minkit.dll` | FindFirstFileA, SetWindowTextA, ShellExecuteExA, CreateFontIndirectA | dialogs `ABOUTDLG`/`PREVIEWDLG`/`SETUPDLG` (screensaver-style config) |
| `MinkIt.dll` 94 KB | **the engine** | CreateFileA, FindFirstFileA, **Get/WritePrivateProfileString**, psapi | none (code only) |
| `Launch.exe` 344 KB | layered transparent mascot launcher | **UpdateLayeredWindow + SetLayeredWindowAttributes**, **TextOutA/DrawTextA**, GetPrivateProfileString, ShellExecuteExA, ws2_32 | menus `IDR_MAINMENU`/`IDR_ITEMMENU`, dialogs `APPNAMEDLG`/`NEWNAMEDLG`/`SETUPDLG`, bitmap `SERIF_BASE` (speech) |
| `WinCalc.exe` 577 KB | Squirrel-scripted calc; gmp/mpfr bignum; msimg32 alphablend | CreateFontA, DrawTextA, UpdateLayeredWindow | menu + 4 dialogs + **string table (IDs 3601–3838)** |

- `MinkIt.dll` reads `[Path]Folder=` from **MinkIt.ini** (GetPrivateProfileString) and opens `.mink`
  via CreateFileA/FindFirstFileA; psapi = the process-watch that triggers the copy animation. It is
  the only code that touches the `.mink` bytes → **start Ghidra here for the a0/m0 codec.**
- `Launch.exe` is the mouse-offset-bug suspect: `UpdateLayeredWindow`/`SetLayeredWindowAttributes`
  per-pixel-alpha window + GDI-drawn text.

### Translation surface (ROI order)
1. **Trivial text edits** — `Launch.ini` `Title###` (アイマス電卓 / らき☆すた電卓 / コピーアニメーション /
   壁紙えらび / Googleカレンダー / 画面のプロパティ), `MinkIt.ini`, wallpaper HTML, `お読みください.txt`.
2. **PE resources (lang 1041)** — dialogs/menus/string-tables in the exes + the 4 `.scr`. Edit with
   `lief` (in-flake, scriptable) or Resource Hacker under wine. Strings are all lang 1041 → swap to
   English (or add a 1033 fork).
3. **In-container text** — ACZ `Ini` (speech), `data.pak` `*.nut` (calc strings) → needs the codec.
4. **`.mink` speech** (if any) — gated behind the a0/m0 codec.

### Locale / path fix — mechanism found
The JP-path dependency = ANSI cp932 `CreateFileA`/`FindFirstFileA`/`GetPrivateProfileString` in
`MinkIt.dll` & `Launch.exe`. Paths come from **plain-text INIs**: `Launch.ini` has absolute
`C:\…\らき☆マス\…` paths; `MinkIt.ini` has `[Path]Folder=`. → **most of the fix is data**: install to
an ASCII dir, rewrite the INIs, rename the JP `.mink`/`.Xvi`/`.scr` filenames to ASCII. Only any
hardcoded-in-binary path would need a byte patch (FindFirstFileA implies wildcard enumeration →
rename-friendly; confirm in Ghidra). **This likely drops the AppLocale / full-JP-locale requirement
with no runtime hook → favors route B (static patcher)**; a thin launcher (set cwd/codepage) stays a
fallback.

### Containers
`MINK` / `ACZ` (.Xvi) / `PACKDATA` (.pak) directory layouts **solved** → [`mink-format.md`](mink-format.md).
`data.pak` = 111 PNG + **4 Squirrel `.nut`**; `.Xvi` = 2 PNG + a compressed `Ini` text blob. Remaining
unknown = the per-blob **codec** (`0xFF`-prefixed LZ/RLE on text blobs; the `38 47 03 01…` stream on
`.mink` a0/m0).

### Corrections to push upstream (projects/minkit-en-patch)
- path = `らき☆マス\{copy,launcher,calc,wallpaper}`, not `らき―copy`.
- compiler = MSVC-2005 native C/C++ (not unknown/packed).
- `.mink` is a *mapped* `MINK` container; only the a0/m0 codec is open.
- launcher & calc are separate, richer sub-apps; calc is Squirrel-scripted; `.Xvi`=`ACZ` and
  `data.pak`=`PACKDATA` are newly-mapped formats.
- bulk of GUI text is standard PE resources → resource-edit; no runtime API hook needed for static UI.

### Env
`nix develop` builds clean (exit 0) — full toolchain (ghidra/rizin/cutter/wrestool/pev/imhex/wine/
qemu/xdelta3/python-construct-lief-pillow) available.

### Next
1. Crack the `0xFF` codec — start with the smallest ACZ `Ini` (plain-text target) → infer opcodes →
   apply to `.nut` → then the `.mink` `a0`/`m0`.
2. Ghidra `MinkIt.dll`: confirm `.mink` filename enumeration vs hardcoded names; locate the a0/m0
   decode routine.
3. `tools/`: container unpack/repack (stored chunks round-trip today; codec gates the rest).
4. Stand up the **wine inner loop** (flake has wine; box has WSLg/GPU) for fast patch iteration.
5. Sync the corrections above into the upstream scope doc.

---

## 2026-06-21 — Session 1 (cont.): codec cracked + container unpacker

- **Codec cracked (for the text):** the ACZ `Ini` blobs are **canonical Okumura LZSS**
  (N=4096 / F=18 / THRESHOLD=2 / ring-init `0x20` / flag-bit-set = literal) — byte-exact on all 22
  launcher files. The "`0xFF` prefix" was just the first all-literal flag byte → [`mink-format.md`](mink-format.md).
- **`tools/sygnas_unpack.py`** (stdlib-only, runs anywhere) parses MINK/ACZ/PACKDATA and LZSS-decodes
  the ACZ text. It extracts the **launcher's entire text surface**: 22 characters ×
  (`Name=` + 10 `Serif*` lines) = **220 dialogue lines**, as editable Shift-JIS INI, plus 44 char PNGs.
- **Scope correction:** the launcher has **22** characters, not 23.
- **`.nut` (calc Squirrel) and `.mink` a0/m0 (sprite) use *other* codecs** — deferred; neither gates
  the TL (calc text is in PE resources; sprites carry no text). Crack via Ghidra if/when wanted.
- **Translation surface — now located + (partly) tooled:**
  - launcher speech → `tools/sygnas_unpack.py` on `*.Xvi` ✅ (editable INI).
  - GUI dialogs/menus/string-tables (lang 1041) → resource edit (lief / Resource Hacker). *[TODO tool]*
  - `Launch.ini` titles + `MinkIt.ini` + wallpaper HTML + `お読みください.txt` → plain-text edits.
- **Next:** (a) an LZSS **repacker** to round-trip an edited `Ini` back into the ACZ (+ re-Inno or
  static patch); (b) a PE-resource string dumper/patcher (lief); (c) lock route A vs B; (d) wine smoke-test.

---

## 2026-06-21 — Session 1 (cont.): repacker + EN launcher translation + deploy

- **Repacker built + verified** (`tools/sygnas_repack.py`): an Okumura-LZSS *encoder* that's
  byte-for-byte decode-compatible (selftest: encode→decode == identity on all 22; output within ~2
  bytes of SYGNAS's own compressor). Fixed one bug — forbid **self-overlapping (RLE) matches** (else
  the decoder reads a byte it writes mid-copy: `crisis since`→`crisisisince`). The per-chunk `tag` is
  a constant type id (`0x8b878b01` for every Ini), **not a checksum** → kept verbatim.
- **Rough EN machine-translation of all 22 launcher characters** (`tools/build_launcher_en.py` →
  `patch/launcher/<char>.ini`): Name + 8 `Serif*` lines each, structure/`[POS]`/`\n`/`<%SCHEDULE%>`
  preserved. Repacked → all 22 round-trip exactly; total `.Xvi` size delta **+436 B**.
- **Deployed to the XP Time Machine** (cold disk, **mounted by NTFS UUID** — the disk re-letters
  sda↔sdb; a first `sda1` attempt mounted Win7's System-Reserved and `set -e`-aborted before any
  write): 22 EN `.Xvi` overwrote `…\らき☆マス\launcher\` (originals →
  `courier:/root/luckymas-launcher-orig.20260621-202727`), deployed bytes `cmp`-verified. Also
  dropped the **SMBus identity INF** (`xp/chipset-inf/smbus_null.inf`) into `C:\WINDOWS\inf\` +
  `C:\retro-kit\chipset-inf\`. Pending the owner's single reboot to test both.
- **Still open:** PE-resource UI strings (lief), `Launch.ini` titles + wallpaper HTML (trivial), the
  `.nut`/`.mink` codecs, route A/B lock-in, wine/QEMU loop.

---

## 2026-06-22 — Session 2: live-test the calendar path → **protocol correction (ClientLogin = HTTPS)**

Built the `tools/gcal-emu/` test-board (session 1) and stood it up to actually drive the launcher's
calendar against it. The enabling infra (in `retro-hardware/projects/xp-remote-probe/`) turned into the
real story; the LuckyMas-relevant findings:

- **gcal-emu hosted + reachable.** Runs on the always-on `code` box behind Caddy (`http://www.google.com`
  vhost → `gcal-emu` on :8091); XP's `hosts` redirects `www.google.com` → `code` (verified: XP
  `ping www.google.com` → `10.0.10.53`). gcal.exe **launches + prompts for a Google account**; the
  seeded `gcal.ini` wasn't in the format it reads, so it shows the login dialog (fine — any creds work
  against the emulator).
- **🔧 PROTOCOL CORRECTION — ClientLogin is HTTPS, not plain HTTP.** On submitting (bogus) credentials,
  gcal.exe errors with WinINet **12157 = `ERROR_INTERNET_SECURITY_CHANNEL_ERROR`** (a JP "secure channel"
  dialog) — i.e. it opens a **TLS** connection for `/accounts/ClientLogin` and the handshake fails (our
  `code:443`/Caddy has no `www.google.com` cert + no XP-era TLS). The session-1 note "all WinINet over
  plain `http://`, NO HTTPS → no cert" was **half-wrong**: the scheme isn't a string in the binary
  (WinINet sets it via a flag/port at runtime — `INTERNET_FLAG_SECURE`/443), so strings-recon couldn't
  see it. Period-correct: Google's 2007 ClientLogin was **HTTPS-only** (credentials over TLS); the
  **GData feeds stay plain HTTP** (their URLs ARE literal `http://…` in `gcalcore.dll`). Real shape =
  **HTTPS login + HTTP feeds**.
  - *RE to pin it (next session, Ghidra):* the dialog's **JP error string** is gcal.exe's own — find it
    in `gcalcore.dll`/`gcal.exe` (wide strings) and xref it; the code just above is the failed
    `InternetConnect`(443)/`HttpOpenRequest`(`INTERNET_FLAG_SECURE`) for ClientLogin → reveals whether it
    validates the cert (⇒ must install our CA in XP's root) or ignores cert errors (⇒ self-signed is
    enough), and the exact TLS/cipher it asks for.
- **⇒ Next step (the open build):** give the emulator an **HTTPS `/accounts/ClientLogin` on :443** with
  (a) a self-signed `www.google.com` cert **installed in XP's Trusted Root store**, and (b) **XP-SP3-era
  TLS** (TLS 1.0 + AES-CBC/3DES — XP can't do modern TLS, and `code`'s Caddy has neither the cert nor the
  old ciphers). Then the feeds (already working over HTTP) should follow → the Serif bubbles fire.
- **Live-control infra built (reusable, not LuckyMas-specific):** a tiny curl-driven agent on XP
  (`xphttpd`, runs as Administrator, real interactive screenshots) + `netexec`/SMB for clean deploys —
  see `retro-hardware/projects/xp-remote-probe/`. This is what made the live recon possible (the Bitvise
  SSH route was a dead end). nircmd does **not** actually hang as Administrator (the session-1 "hang" was
  a Startup-batch context artifact); but nircmd with **no/garbled args pops a modal** that wedges a
  single-threaded caller — that DID look like the hang.

---

## 2026-06-22 — Session 3: pivot to a native XP-local server; XP-era TLS proven

- **Decision (owner-directed):** build the calendar/mail server **natively on XP** (Schannel HTTPS +
  plain-socket HTTP/POP3), not on a separate box. Rationale + target architecture →
  [`next-builds.md`](next-builds.md) §"Session 3". The win: server (Schannel) and client (gcal.exe
  WinINet) are the **same 2007 stack**, so the TLS handshake is period-accurate by construction — no
  modern-TLS coercion, no separate always-on host.
- **XP-era TLS handshake de-risked (local proof).** Added an HTTPS listener to `gcal_emu.py` (`--https`)
  with a self-signed `www.google.com` cert (**RSA-2048, SHA-1**, CN+SAN, 20y — `make-xp-cert.sh`,
  `certs/`). A TLS1.0 + **AES128-SHA** (RSA-kx CBC) client — XP SP3's exact capability — completes the
  handshake and gets `Auth=` over TLS. ⇒ XP's WinINet will handshake our cert; the native Schannel server
  reproduces the same suite.
  - **OpenSSL 3.x gotcha (cost ~an hour):** to serve TLS1.0 you must drop the security level with a
    **colon-separated** token — `set_ciphers('…:@SECLEVEL=0')`. Without the colon (`…SHA@SECLEVEL=0`) the
    seclevel stays ≥1 and the server rejects the TLS1.0 ClientHello with a **`protocol_version` alert
    (70)** — looks like "TLS1.0 unsupported" but it's a seclevel artifact. nixpkgs OpenSSL 3.6 *does*
    support TLS1.0.
- **Infra finding:** `code`'s Caddy **wildcard-binds `*:80`/`*:443`**, so a secondary IP (`10.0.10.54`)
  can't host `:443` either → the code-hosting route is a dead end for the HTTPS endpoint. Moot now (XP-local
  `hosts → 127.0.0.1`). Scaffolding torn down; Caddy left intact.
- **Cert trust:** the native server **installs the self-signed cert into XP's Root by default**
  (`CertAddEncodedCertificateToStore`); WinINet won't trust self-signed otherwise, harmless if it ignored
  cert errors → no separate trust-probe needed.
- **Live infra confirmed this session:** xphttpd agent live at **10.0.10.113:8099** (`/run` ok, XP SP3);
  `ssh root@code.soy` works (LAN tooling, `nix run nixpkgs#netexec`); i686 mingw cross-gcc fetchable via
  `nix … pkgsCross.mingw32.buildPackages.gcc` (cached, ~79 MiB).

---

## 2026-06-22 — Session 4: native server BUILT + Schannel handshake PROVEN on real XP 🎉

Built `tools/gcal-xp/gcalsrv.c` — the native XP-local fake-Google server — and validated it end-to-end
against the **real XP WinINet/Schannel stack**. **The Schannel side is figured out.**

**What it is.** One self-contained Win32 EXE (i686, XP subsystem 5.1, 80 KB, statically linked → imports
only XP system DLLs): plain-Winsock **HTTP feeds :80** + **POP3 :110**, **Schannel HTTPS `/accounts/ClientLogin`
:443**, with the self-signed `www.google.com` cert embedded as a PKCS#12 blob (`cert_pfx.h`). Response logic
ported from the `gcal_emu.py` oracle; rich per-request file logging (`gcalsrv.log`). Build: `build.sh`
(mingw via nix). Files: `gcalsrv.c`, `cert_pfx.h`/`embed-pfx.sh`, `build.sh`, `test/clientlogin.vbs`, `README.md`.

**Proven on the live box (10.0.10.113):** an XP **WinINet** client (`MSXML2.XMLHTTP`, the same stack
`gcal.exe` uses — `test/clientlogin.vbs`) POSTed ClientLogin over TLS and got `STATUS=200` +
`Auth=EMU_TEST_TOKEN`. Server log: `TLS 127.0.0.1: handshake complete → POST /accounts/ClientLogin → 200`.
So WinINet↔Schannel handshake **completes**, the self-signed cert is **trusted** (Root install worked), and
ClientLogin returns `Auth=`. The HTTP Atom feeds (allcalendars list + anchored event feed) + POP3 STAT were
also verified live. ⇒ the pivot's premise (XP WinINet ↔ XP Schannel = the same 2007 stack → period-accurate
by construction) is **confirmed**.

**Bugs found + fixed this session (all on the live box):**
- **PKCS#12 must use XP-legacy PBE.** OpenSSL 3.x defaults to PBES2/AES-256/SHA-256 which XP's
  `PFXImportCertStore` can't parse → make the PFX with `-legacy -keypbe PBE-SHA1-3DES -certpbe PBE-SHA1-3DES
  -macalg sha1` (`embed-pfx.sh`).
- **mingw `-lmcfgthread` / XP-safety.** nixpkgs mingw libgcc is `--enable-threads=mcf`; link it via
  `-L$(nix build …windows.mcfgthreads)/lib -static` → the mcf code is dead-stripped (we use native
  `CreateThread`, per owner), the EXE imports only XP DLLs (verified, no post-XP API). `-no-pie` = fixed base.
- **Protected-root MODAL hang.** `CertAddEncodedCertificateToStore(…Root…)` pops XP's "install this root?"
  confirmation **dialog**, which blocked the single-threaded startup before the listeners bound (owner
  clicked Yes → it proceeded; cert now in CurrentUser\Root + LocalMachine\Root). Fix: cert install moved to a
  **background thread** after the listeners are up + a `--no-cert` flag; for unattended installs use
  certutil/registry (see README TODO).
- **Crash on a rejected handshake.** `openssl s_client`'s modern ClientHello is rejected by XP's 2007
  Schannel with `SEC_E_INVALID_TOKEN` (0x80090308) — *not* a problem for real WinINet, but my failure path
  called `DeleteSecurityContext` on a never-created context → access violation → crash popup. Fix: only delete
  if a context was created + `SetErrorMode(SEM_NOGPFAULTERRORBOX…)` so a server fault can never block the box.
- **SYSTEM keyset.** Launched headless via SMB-exec (wmiexec = SYSTEM), `PFXImportCertStore` fails with
  `NTE_BAD_KEYSET` (0x8009000b); user keyset only works in an interactive session → **fall back to
  `CRYPT_MACHINE_KEYSET`**. Now works both as the interactive user (deliverable) and as SYSTEM (test).

**Operational lessons (now in CLAUDE.md):** the **xphttpd agent is single-threaded** — a forever-running
child (e.g. the server) inherits its stdout pipe and **wedges** it. ⇒ drive everything via **SMB-exec
(`nix run nixpkgs#netexec`)** and reserve the agent for **screenshots only**. The headless server runs fine
as SYSTEM in session 0 (ports are global; loopback crosses sessions; trust via LocalMachine\Root). TODO:
fix the agent's single-threadedness, or see if `smbexec -i 1` can run on the interactive desktop.

**✅ Lua migration done + validated (same session).** Embedded **Lua 5.4** (statically linked, compiled from
the nix-pinned source → `liblua.a`; the EXE still imports only XP DLLs, now ~300 KB). C keeps the transport
(sockets, Schannel, POP3 framing, HTTP status/headers, cert); **all request logic moved to `gcalsrv.lua`**
(routing, Atom builders, ClientLogin/POP3 responses, `gcal-xp.ini`). C↔Lua boundary = `http_handle()` +
`pop3_event()`; one shared `lua_State` under a lock (low volume). The script is embedded (`gcalsrv_lua.h` via
`embed-lua.sh`) with an external `<exedir>\gcalsrv.lua` override → a real local-calendar backend is now a script
edit. **Re-validated on XP via SMB-exec:** WinINet TLS ClientLogin (`STATUS=200`, `Auth=`), the HTTP Atom feeds,
and POP3 (incl. multi-line LIST) — all **byte-identical** to the C version.

**✅ End-to-end captured on real XP (same session).** Drove the actual launcher against our Lua server and
screenshotted the mascot bubbles (→ `docs/screenshots/`, README gallery). `gcalcore` did the full check —
`ClientLogin` over Schannel TLS → `Auth=` → allcalendars → the event feed, and the binary's **real** query is
`…/private/full?start-min=<today>T00:00:00+09:00&start-max=<tomorrow>T00:00:00+09:00` — and the EN-translated
**`SerifCallenderSchedule`** bubble rendered with our events (Dentist / Lunch with Konata / Buy doujinshi);
**`SerifCallenderNone`** ("No plans!…") rendered too.
- **Bubble triggers:** the boot check (`[Calendar] Boot=1`) auto-pops a bubble only when there ARE events
  (Schedule). An empty calendar is **silent on boot**; `SerifCallenderNone` fires on the **manual right-click
  → Calendar check (&C)** (owner confirmed live).
- **Screenshot gotcha:** the mascot is a per-pixel-alpha **layered window** — `nircmd savescreenshotfull`
  (GDI BitBlt) captures it as **bare desktop**. Use **PrtScn → clipboard → save** (`nircmd sendkeypress 0x2c`
  then `nircmd clipboard saveimage`) to grab the composited framebuffer.
- **JP-path + agent gotchas:** the JP install path breaks cmd `start`/`cd` → copy the launcher to an ASCII
  path (`C:\lm`, `Launch.ini` `Folder=C:\lm`). The single-threaded xphttpd agent wedges if a launched GUI holds
  its stdout pipe; **`nircmd exec show <fullpath>`** detaches cleanly (no wedge), `start`/`start …>nul` did not.
  And `nircmd savescreenshotfull` fails if a *preceding* chained command used `>nul` (the nul handle leaks as
  its stdout) — delay with `ping` **without** `>nul`. Driver: `tools/gcal-xp/test/lm.cmd`.

**Remaining:** silent (no-modal) cert install + first-run installer; patch `gcalcore.dll`'s host string
(wide `www.google.com`) → `localhost` so the redirect doesn't blackhole real Google; finish the EN text +
PE-resource strings; the POP3 mail bubble (Launch.ini `[Mail]` needs a configured POP3 client/host).
