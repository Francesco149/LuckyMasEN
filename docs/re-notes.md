# MinkIt / Lucky☆Mas — RE log

Running reverse-engineering notes. Format specs: [`mink-format.md`](mink-format.md).

---

## 2026-06-21 — Session 1: extraction + first recon

### Acquisition (no XP-disk pull needed)
Local kit ISO on the dev box → `setup.exe` = **Inno Setup 5.1.10** (app "らき☆マス デスクトップアクセサリ
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
- **Deployed to a real XP box:** 22 EN `.Xvi` overwrote `…\らき☆マス\launcher\` (originals backed up
  first), deployed bytes `cmp`-verified. Pending a reboot to test.
- **Still open:** PE-resource UI strings (lief), `Launch.ini` titles + wallpaper HTML (trivial), the
  `.nut`/`.mink` codecs, route A/B lock-in, wine/QEMU loop.

---

## 2026-06-22 — Session 2: live-test the calendar path → **protocol correction (ClientLogin = HTTPS)**

Built the `tools/gcal-emu/` test-board (session 1) and stood it up to actually drive the launcher's
calendar against it. The enabling XP-deployment infra turned into the
real story; the LuckyMas-relevant findings:

- **gcal-emu hosted + reachable.** Runs on a separate build box behind a reverse proxy (`http://www.google.com`
  vhost → `gcal-emu` on :8091); XP's `hosts` redirects `www.google.com` → that box (verified: XP
  `ping www.google.com` resolves to it). gcal.exe **launches + prompts for a Google account**; the
  seeded `gcal.ini` wasn't in the format it reads, so it shows the login dialog (fine — any creds work
  against the emulator).
- **🔧 PROTOCOL CORRECTION — ClientLogin is HTTPS, not plain HTTP.** On submitting (bogus) credentials,
  gcal.exe errors with WinINet **12157 = `ERROR_INTERNET_SECURITY_CHANNEL_ERROR`** (a JP "secure channel"
  dialog) — i.e. it opens a **TLS** connection for `/accounts/ClientLogin` and the handshake fails (our
  test server's `:443` had no `www.google.com` cert + no XP-era TLS). The session-1 note "all WinINet over
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
  TLS** (TLS 1.0 + AES-CBC/3DES — XP can't do modern TLS, and the test server had neither the cert nor the
  old ciphers). Then the feeds (already working over HTTP) should follow → the Serif bubbles fire.
- **Live-control infra built (reusable, not LuckyMas-specific):** a remote-control path to drive a real
  XP box (launch GUI apps, take screenshots) plus a clean file-deploy path. This is what made the live
  recon possible (the Bitvise SSH route was a dead end). nircmd does **not** actually hang in an elevated
  session (the session-1 "hang" was a Startup-batch context artifact); but nircmd with **no/garbled args
  pops a modal** that wedges a single-threaded caller — that DID look like the hang.

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
- **Infra finding:** the separate-host route is a dead end for the HTTPS endpoint. Moot now (XP-local
  `hosts → 127.0.0.1`). Scaffolding torn down.
- **Cert trust:** the native server **installs the self-signed cert into XP's Root by default**
  (`CertAddEncodedCertificateToStore`); WinINet won't trust self-signed otherwise, harmless if it ignored
  cert errors → no separate trust-probe needed.
- **Live infra confirmed this session:** a real XP SP3 box is reachable for remote deploy/drive; i686
  mingw cross-gcc fetchable via `nix … pkgsCross.mingw32.buildPackages.gcc` (cached, ~79 MiB).

---

## 2026-06-22 — Session 4: native server BUILT + Schannel handshake PROVEN on real XP 🎉

Built `tools/gcal-xp/gcalsrv.c` — the native XP-local fake-Google server — and validated it end-to-end
against the **real XP WinINet/Schannel stack**. **The Schannel side is figured out.**

**What it is.** One self-contained Win32 EXE (i686, XP subsystem 5.1, 80 KB, statically linked → imports
only XP system DLLs): plain-Winsock **HTTP feeds :80** + **POP3 :110**, **Schannel HTTPS `/accounts/ClientLogin`
:443**, with the self-signed `www.google.com` cert embedded as a PKCS#12 blob (`cert_pfx.h`). Response logic
ported from the `gcal_emu.py` oracle; rich per-request file logging (`gcalsrv.log`). Build: `build.sh`
(mingw via nix). Files: `gcalsrv.c`, `cert_pfx.h`/`embed-pfx.sh`, `build.sh`, `test/clientlogin.vbs`, `README.md`.

**Proven on the live XP box:** an XP **WinINet** client (`MSXML2.XMLHTTP`, the same stack
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
- **SYSTEM keyset.** Launched headless as LocalSystem (session 0), `PFXImportCertStore` fails with
  `NTE_BAD_KEYSET` (0x8009000b); user keyset only works in an interactive session → **fall back to
  `CRYPT_MACHINE_KEYSET`**. Now works both as the interactive user (deliverable) and as SYSTEM (test).

**Operational lessons:** launch a forever-running child (the server) detached so it doesn't inherit and
wedge the launcher's stdout pipe; reserve interactive control for **screenshots only**. The headless
server runs fine as SYSTEM in session 0 (ports are global; loopback crosses sessions; trust via
LocalMachine\Root).

**✅ Lua migration done + validated (same session).** Embedded **Lua 5.4** (statically linked, compiled from
the nix-pinned source → `liblua.a`; the EXE still imports only XP DLLs, now ~300 KB). C keeps the transport
(sockets, Schannel, POP3 framing, HTTP status/headers, cert); **all request logic moved to `gcalsrv.lua`**
(routing, Atom builders, ClientLogin/POP3 responses, `gcal-xp.ini`). C↔Lua boundary = `http_handle()` +
`pop3_event()`; one shared `lua_State` under a lock (low volume). The script is embedded (`gcalsrv_lua.h` via
`embed-lua.sh`) with an external `<exedir>\gcalsrv.lua` override → a real local-calendar backend is now a script
edit. **Re-validated on real XP:** WinINet TLS ClientLogin (`STATUS=200`, `Auth=`), the HTTP Atom feeds,
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
- **JP-path + launch gotchas:** the JP install path breaks cmd `start`/`cd` → copy the launcher to an ASCII
  path (`C:\lm`, `Launch.ini` `Folder=C:\lm`). A single-threaded caller wedges if a launched GUI holds
  its stdout pipe; **`nircmd exec show <fullpath>`** detaches cleanly (no wedge), `start`/`start …>nul` did not.
  And `nircmd savescreenshotfull` fails if a *preceding* chained command used `>nul` (the nul handle leaks as
  its stdout) — delay with `ping` **without** `>nul`. Driver: `lm.cmd` (the on-XP launcher driver).

**Remaining:** silent (no-modal) cert install + first-run installer; patch `gcalcore.dll`'s host string
(wide `www.google.com`) → `localhost` so the redirect doesn't blackhole real Google; finish the EN text +
PE-resource strings; the POP3 mail bubble (Launch.ini `[Mail]` needs a configured POP3 client/host).

---

## 2026-06-22 — Session 5: reproducible patch system + translation wins + host→localhost

Owner-directed: make patching **reproducible + tracked** (one auditable pipeline, building toward an
**English installer re-wrapped from the user's own `setup.exe`**), and continue the handoff. Architecture
→ [`patch-system.md`](patch-system.md).

- **Built the patch pipeline.** `patch/manifest.toml` (declarative single-source-of-truth: every patched
  file + op + note) + `tools/build_patch.py` (mirrors `originals/installed/` → `out/patched/`, applies ops,
  writes `PATCH-LOG.txt`). Ops: `xvi` / `text_keys` / `text_subst` / `text_file` / `binpatch` / `rename`;
  `active=false` records intent without applying. **Reproducible** (two builds hash-identical) and the 22
  `.Xvi` round-trip (selftest 22/0). The launcher repack is now pipeline-driven, not a manual step.
- **Translation wins (display text):** `Launch.ini` menu titles, the readme (お読みください.txt), and the
  wallpaper picker UI — all English.
- **🔑 Locale-safety rule (project goal #2).** App-read text goes through ANSI APIs
  (`GetPrivateProfileStringA`, `DrawTextA`) → non-ASCII mojibakes on a non-JP box. So **app-read text must be
  pure ASCII** ("Lucky Star", not "Lucky☆Star"); Notepad-only text (readme) → **UTF-8 + BOM** (XP Notepad
  honours it on any locale, keeps ☆/×); HTML → UTF-8 (meta charset). The `.Xvi` serifs still carry a few `☆`
  → ASCII pass is a follow-up. File paths (`らき☆マス`, JP `.mink`/`.scr`) must become ASCII too → tracked
  deferred (needs the install at the ASCII path, which the installer pins).
- **🔧 host→localhost — RE correction to the handoff.** The wide host string is in **both binaries**, not
  just `gcalcore.dll`:
  - `gcalcore.dll` ×2: bare `www.google.com` + the `http://www.google.com/.../allcalendars/full` URL.
  - `gcal.exe` ×3: same two **plus** the browser add-event deep-link
    (`…/calendar/event?action=TEMPLATE&dates=…`).
  - `Launch.exe`: only bare `google`/`POP3` *labels* — no connectable host (POP3 host comes from
    `Launch.ini [Mail]`, deferred).
  All MFC-Unicode WinINet → wide only. `binpatch` replaces each **complete NUL-terminated** string
  (`www.google.com\0\0` matches the bare host, not the substring inside the URLs), writing the shorter
  `localhost` in place + zero-padding the freed tail → **size unchanged, PE valid**. After this the XP
  `hosts` line is dropped (real Google browsing restored).
- **Server side matched:** `gcalsrv.lua` now returns a **`localhost`** event-feed link (works for both the
  byte-patch and the legacy hosts-redirect, since localhost always → 127.0.0.1), and the embedded cert is
  regenerated **CN=localhost** (SAN `localhost,127.0.0.1,www.google.com,google.com,*.google.com` so the
  legacy path still validates). `gcalsrv.exe` rebuilt (XP-only imports ✓); `clientlogin.vbs` now defaults to
  `https://localhost/...`.
- **Deferred + recorded** (flip `active=true` once RE-confirmed): Launch.ini install-root path rewrite;
  `.mink` (10) / `.scr` (4) / wallpaper-JPG renames; `MinkIt` copy-engine path config (no INI ships →
  RE where it reads its folder); `autorun.inf`; PE-resource UI strings (lang 1041).

**✅ Live test PASSED on real XP, owner-driven.** Deployed to the XP box (kill+del before overwrite to
avoid SHARING_VIOLATION; the protected-root cert modal; layered-window screenshots via PrtScn). Patched
launcher → `C:\lm`, rebuilt `gcalsrv.exe` → `C:\gcal-xp`,
hosts line dropped. Validated: WinINet **ClientLogin TLS → localhost** (STATUS=200, `Auth=`), allcalendars
+ event feed (200), the EN **SerifCallenderSchedule** bubble rendered hiyori's served events (re-fires on
manual check), and **google.com is still reachable** (real internet intact — the byte-patch replaced the
hosts blackhole). Cert trust = one owner click on the protected-root modal (XP has no certutil for a
silent install). The stale `gcalsrv.c` log line now reads the cert CN instead of hardcoding it.
- **Working:** the calendar bubble + the **left-click app list** (EN `Title###`).
- **🎯 Still JP = PE-resource strings in `Launch.exe` (lang 1041) — the next translation stage (`pe-res`
  op), precisely scoped by the owner's live test:** the **right-click main menu** (settings/exit/calendar
  + mail check), the **per-app item context menu** (`(&T)`/`(&D)` = rename/delete → `IDR_ITEMMENU`), and
  the **pin/hold arrow tooltip** (bottom-right — confirm PE-resource string vs hardcoded).

**Remaining:** PE-resource TL (the menus/tooltip above + the rename dialogs `APPNAMEDLG`/`NEWNAMEDLG`); the
`.Xvi` ASCII pass; the POP3 mail bubble; then the **installer re-wrap** (ISCC under wine).

### PE-resource translation — `Launch.exe` menus + dialogs DONE (owner-validated on real XP)
New tool `tools/pe_res.py` (+ a `pe_res` op in `build_patch.py`): dumps and **surgically** patches PE-resource
strings (RT_MENU + RT_DIALOG, lang 1041), keyed by exact JP source string (one map per binary; shared strings
like ｷｬﾝｾﾙ/Cancel translate once). PE-resource text is **Unicode** (drawn by the Unicode menu/dialog APIs) →
renders on any locale, no ASCII constraint (unlike the ANSI-drawn `.Xvi` serifs / Launch.ini).
- **🩹 Do NOT use `lief.write()` to repackage these PEs.** It rebuilds the whole PE (adds a 5th section,
  +114 KB) and the result **crashes on XP** — the Settings dialog crashed even though lief preserved every
  resource leaf **byte-identical** (16/16 non-menu leaves unchanged). So the structural rebuild is the
  culprit, not the resource content. Fix: a **surgical** patcher — rewrite only the changed menu/dialog blobs
  (in place, or appended into `.rsrc`'s file-alignment slack), and fix just that data-entry's (RVA,Size) +
  `.rsrc` VirtualSize + SizeOfImage + the PE checksum. Result: **file size unchanged, ~hundreds of bytes
  differ, every other byte (all dialogs/imports/relocs) identical** → no collateral breakage. The labels are
  `id=0xFFFF` (IDC_STATIC) so target controls by **index**, not id, if ever doing geometry.
- **DLGTEMPLATE/DLGTEMPLATEEX parser+rebuilder** in `pe_res.py` — round-trips **byte-identical** with an empty
  map (the faithfulness test gating the patcher). Handles sz_Or_Ord, DS_SETFONT, DWORD-aligned items, EX.
- **Translated:** IDR_MAINMENU + IDR_ITEMMENU; SETUPDLG (settings), APPNAMEDLG (set title), NEWNAMEDLG (save
  as) — 31 strings. **Layout note:** the JP controls are sized tight; EN labels clip/wrap, so SETUPDLG labels
  are kept **concise to fit the original widths** (Folder / Char / Interval / Client / Host→POP3 / Acct / Pass
  …). A full relayout = editing DLGITEMTEMPLATE geometry (by index); deferred unless wanted.
- **`MinkIt.exe` + `WinCalc.exe` DONE** (same surgical op): MinkIt config dialogs (About/Preview/Setup, 11
  strings); WinCalc menu + dialogs (10 strings). Sizes unchanged, PEs valid. `has_jp()` now matches actual
  kana/CJK (not any non-ASCII) so EN strings with ☆/× aren't false-flagged.
- **Scoping found while surveying the rest:**
  - `WinCalc.exe` is **not launched** by the launcher — `Launch.ini` runs the themed **`WinCalcImas.exe` /
    `WinCalcLucky.exe`**, which have **no menu/dialog resources** (icons/manifest only); their UI text lives
    in their `.nut` scripts (`data.pak`, behind the un-cracked codec → deferred). So the calc's on-screen
    text is **not** PE-resource-translatable today.
  - `WinCalc.exe`'s **RT_STRING** table is standard **MFC framework** boilerplate (document/print/window
    prompts) — never shown → **skipped** (no string-table builder needed yet).
  - The 4 **`.scr`** have **no translatable PE strings** (their config dialogs are lang-1033 MFC stubs with
    no text); the dropdown name = the **filename** → handled by the deferred `.scr` **rename**, not resources.
- **⇒ PE-resource translation is COMPLETE** for everything that's resource-translatable + user-visible.
  **Remaining JP is binary/hardcoded strings** — next session (post-/clear): the pin/hold-arrow **tooltip**
  and any other strings drawn via `*A` APIs straight from the binaries (RE + `binpatch`); also the `.Xvi`
  serif **☆→ASCII** locale pass.

---

## 2026-06-22 — Session 7: binary / hardcoded-string translation (all of it) + `.Xvi` ASCII pass

The handoff surface — JP that's NOT in PE resources, drawn at runtime from string literals compiled
into the binaries (`AppendMenuA` / `DrawTextA` / `MessageBox` / `SHBrowseForFolder`). `pe_res.py` can't
see these. **Done end-to-end; build reproducible; sizes byte-preserved; owner live-test pending.**

### New recon tool — `tools/scan_jp.py`
`strings -e s` can't see cp932 (SJIS lead bytes are >0x7F → a JP run looks like garbage); `strings -e l`
floods you with .rsrc + no section context. `scan_jp.py` segments a PE into **NUL-terminated cp932**
literals (strict full-decode + all-printable → kills machine-code/pointer-table noise) and **UTF-16LE**
runs, keeps only real kana/kanji (`pe_res.has_jp`), and reports each unique string with its **PE section**
(tell a `.rdata`/`.data` hardcoded literal from an already-handled `.rsrc` resource), **occurrence count**
(binpatch needs a unique match), and offset. Flags: `--enc cp932|utf16|both`, `--min`, `--min-jp`,
`--section` (default skips `.text`/`(hdr)` where literals never live).
- **Scan gotchas learned:** `.text`/headers are full of false-positive cp932 runs (filter by section);
  a `.rdata` **pointer table** decodes as 2-char halfwidth-kana fields (filter `--min 3 --min-jp 2`);
  **ASCII misread as wide** gives CJK codepoints (`"So"`→`潓`) — for wide, require ≥2 **kana** + ≥90%
  "clean JP/ASCII". The CRT locale strings `ﾁ｣ﾚ｣`/`蠅陲[` appear in `.data` of **every** binary (ignore).

### `binpatch` gains a cp932 mode (`build_patch.py`)
Was `wide` bool (UTF-16LE, 2-byte NUL) | latin1. Now `_binpatch_enc(e)`: `wide=true` → UTF-16LE;
else `encoding` (default latin1) with a **1-byte NUL** → set **`encoding="cp932"`** for SJIS literals.
`old` encodes cp932 to match the image bytes; `new` is ASCII (cp932 passes ASCII through) + shorter →
fits + NUL-pads. **Budget rule:** a JP char is 2 (wide) or 1–2 (SJIS) bytes, EN is 1 → narrow has tons
of room; **wide is in CHARACTERS** and EN is usually *longer* than JP, so only wide strings whose JP
char-count is inflated by embedded ASCII (`%d`, `Result Code`) leave room (see below).

### What was patched (all `n=1` unique, size-preserving, JP gone, EN present — verified both directions)
- **MinkIt.exe** (14, **cp932**): tray menu (`設定(&S)...`→`Options(&S)` — 11B can't fit `Settings(&S)...`;
  `終了(&X)`→`Exit(&X)`); the **Setup "Event type" combo** (5 file-event labels: To Recycle Bin / Empty
  Bin / Download from Internet / Delete / Copy/Move file); Preview defaults `(無題)`/`(不明)`→`(none)`/`(unk.)`
  + `%sのﾌﾟﾚﾋﾞｭｰ`→`%s Preview`; the Startup tooltip, folder-picker title, force-quit MsgBox. **MinkIt has
  no RT_MENU** (confirmed) → the tray menu IS these literals. **Preview Title/Author come from these
  defaults, NOT the `.mink`** — the `info` chunk is a shared codec table, not per-file metadata
  (`mink-format.md`), so no `.mink` data patch is needed.
- **MinkIt.dll** (1, cp932): `初期化に失敗しました`→`Failed to initialize`.
- **Launch.exe** (16, cp932): the **pin/hold-arrow tooltip** `このﾎﾞﾀﾝを押してｱﾌﾟﾘをﾄﾞﾛｯﾌﾟ`→`Drop an app on
  this button` (the owner-flagged one), folder/file dialog titles, the `(*.*)` file filter (kept the `\t`
  field separators), confirm/validation MsgBoxes, the `・・・`→`...` button label.
- **gcal.exe** (9 cp932 + 9 wide): the GDI+ image-loader errors (casual `〜っす` style, **narrow** → would
  mojibake) ASCII-ized; **wide** (MFC-Unicode) status/error/prompt: `Loading...` (the two `〜を取得して
  います` status lines collapse to a generic — wide budget is chars, EN is longer), `Select a calendar.`,
  `Network error`/`Auth error.`/`Exception` (kept the embedded `%d`/`%s`/`Result Code` structure exactly),
  the `gcalcore.dll` path-info error, the Winsock-init error.
- **gcalcore.dll** (3 wide): path-info + `例外`/`通信` errors (same wide strings as gcal.exe).

### Left as-is (recorded; NOT user-facing runtime text)
- **`ＭＳ Ｐゴシック` / `ＭＳ ゴシック`** — `CreateFontA` serif/dialog **facenames**, not displayed text.
  cp932 → could mis-resolve on a non-JP ACP (the Latin alias "MS PGothic" likely works), but changing a
  face risks serif rendering → **deferred; needs a live test** that "MS PGothic"/"MS Gothic" resolves.
- **MFC AppWizard boilerplate** (`アプリケーション ウィザードで生成された…`) + dialog/version **TODO**
  placeholders (`TODO: <ファイルの説明>` = the VERSIONINFO FileDescription, shows only in Explorer
  Properties→Details) — dev leftovers / metadata, belong to the installer/version-stamp stage.

### `.Xvi` serif `☆→ASCII` pass — fixed at the generator (`build_launcher_en.py` = source of truth)
Scan of `patch/launcher/*.ini` found `☆`×5 (akira), `♪`×4 (amimami/azusa/haruka/miki), and — the real
bug — **amimami had leftover untranslated JP**: MT-junk `→` in two serifs, and its **schedule-comment
line lacked the leading `;`** (a SYGNAS inconsistency: amimami's source is bare `セリフ：カレンダー：予定
アリ`) so it missed `COMMENTS{}` and passed through as raw cp932. Fixes (in the generator, so a regen can't
re-introduce them): (1) `transform()` now tolerates a comment missing its `;`; (2) rewrote amimami's two
junk-`→` serifs + dropped azusa's redundant `~` before `♪`; (3) global map adds `☆/★/♪`→`~`, fullwidth
`：`→`:`, `　`→` `; (4) a **pure-ASCII assertion** (`raise SystemExit` if any byte >0x7E survives) — a
permanent locale-safety guard for goal #2. Regenerated → **all 22 INIs pure ASCII**, `.Xvi` Ini round-trips
**byte-exact**.

### Verification
`build_patch` applies 15 ops; **two builds hash-identical** (reproducible). Each touched binary: **size
unchanged**, small localized byte-diff; re-scan shows **no real JP remains** (only float/pointer/CRT
noise + the deferred facenames); every new EN string present `n=1`. The wide binpatch on gcal/gcalcore
is the same op proven safe on these exact files by the Session-5 host→localhost patch (XP doesn't verify
user-mode PE checksums; binpatch leaves them stale, harmless — `pe_res` re-fixes Launch/MinkIt last).
- **Known cosmetic (not a regression):** `scan_jp` surfaces leftover **wide JP** in Launch.exe/MinkIt.exe
  (`MinkIt!について`, `今すぐﾒｰﾙをﾁｪｯｸ(&M)`, …) — these are **dead `pe_res` relocation residue**: when an EN
  menu/dialog blob is longer than the JP, `pe_res` writes it into `.rsrc` slack and **repoints the RVA**,
  leaving the old JP blob as unreferenced bytes (the live, repointed resource is EN — verified each JP
  residue has its EN twin present `n=1`). Invisible to the user; the app reads via the repointed RVA. A
  future tidy-up (zero the old blob after relocating in `pe_res.patch`) would scrub it — deferred (the
  live rendering was XP-validated in Session 6; not worth touching that path now).
**⇒ Remaining = owner live-test on XP (the menus/tooltip/messages render EN), then the installer re-wrap.**

## 2026-06-22 — Session 8: host→localhost VALIDATED on real XP
Closed the one loose end from Session 5: the `host→localhost` + `CN=localhost` cert path was "build side
done" but never cleanly proven on the box.

- **Found a stale-binary gap.** XP was running an old `gcalsrv.exe` whose log reported `cert CN=www.google.com`
  (the CN is read live via `CertGetNameStringA` — not hardcoded — so it was real). The committed *source* +
  `cert_pfx.h` were already `CN=localhost` (openssl-confirmed: CN=localhost, SAN localhost/127.0.0.1/
  www.google.com/…). `gcalsrv.exe`/`gcalsrv_lua.h` are **gitignored build artifacts** → the deployed binary
  had drifted from source. Lesson: always `build.sh` before trusting a deployed gcalsrv.
- **Rebuilt** via `tools/gcal-xp/build.sh` (kept the CN=localhost `cert_pfx.h`; regen lua; imports = XP DLLs only),
  redeployed, **started on the XP box**, and **proved end-to-end**:
  - server log: `cert CN=localhost` · `gcalsrv ready (3 listeners)` · `cert: install -> CurrentUser\Root: ok`
    + `LocalMachine\Root: ok` (installed **silently as SYSTEM**, no modal; owner also approved the interactive
    cert prompt) · `TLS 127.0.0.1: handshake complete` → `POST /accounts/ClientLogin -> 200`.
  - client (`clientlogin.vbs`, default host=localhost, = gcal.exe's WinINet stack): `URL=https://localhost/…`
    `STATUS=200 OK` `Auth=EMU_TEST_TOKEN`. ⇒ WinINet **trusts CN=localhost** over TLS to `https://localhost`
    with **no hosts redirect** (`hosts` = `127.0.0.1 localhost` only). The deliverable's whole TLS layer holds.
- **Operating-mode discoveries:** remote inline-command output is flaky → have the remote run a **`.bat`
  that redirects to a file**, then fetch the file. Launching a persistent EXE remotely: **`start` from a
  session-0 context fails silently** (window station) and **`schtasks /create /f` fails on XP** (`/f` is
  Vista+); ✅ a **direct exec** of `C:\gcal-xp\gcalsrv.exe` works (GUI-subsystem → the launching `cmd /c`
  returns at once, the process persists). Silent SYSTEM cert install (both Root stores) → useful for the
  installer stage.
- **Live GUI test PASSED (owner-driven, owner present):** redeployed the latest `out/patched/` launcher to
  `C:\lm`, owner drove it. Confirmed on real XP: the **`SerifCallenderSchedule` bubble fires** through the
  real launcher (full localhost path end-to-end), the **serif font renders clean** (⇒ the held-back
  `ＭＳ Ｐゴシック` facename stays JP — no patch needed), and the Session-7 EN strings render: right-click
  menus, the **pin tooltip** ("Drop an app on this button"), the **mail-interval validation** message, and
  the delete-app confirm.
- **Two follow-up fixes (owner-requested; done + redeployed + owner-confirmed):**
  1. **GoogleAccount dialog** — `DIALOG/129` ("GoogleAccount の設定" + "キャンセル") lives in **gcal.exe AND
     gcalcore.dll**; it was binpatched but never `pe_res`'d, so it stayed JP (it's an RT_DIALOG lang 1041 —
     NOT locale-controlled, as first suspected). Added a `pe_res` pass to both → "Google Account Settings" /
     "Cancel" (OK/Email/Password already EN). Sizes unchanged, PEs valid; the other gcal dialogs (102
     TODO-placeholder, 182 `オン1`×8, MFC 30721) stay untouched (`pe_res` only rewrites blobs with a hit).
  2. **Star convention** — owner: render the JP `☆`. **Product/franchise NAMES → `*`** (`Lucky*Mas`,
     `Lucky*Star Calculator`; in the manifest: HTML title/h1, WinCalc About, Launch.ini Title001, readme).
     **Decorative serif tics → `~`** (in `build_launcher_en.py`; the bubbles carry only decorative stars, no
     names → `Kyaan~`, `out~`). Filenames stay `*`-free (`*` is illegal in Windows paths → the deferred
     `.scr` rename target uses "Lucky Star"; display name will use `*` at the future `.scr` pe_res stage).
- **Known issue — deferred to post-translation polish (owner-flagged, pre-existing in the JP build):** a
  spurious **empty app-launcher menu** sometimes appears on left-click of the launcher. NOT a TL regression;
  investigate as extra polish after the translation + installer work.
- Note: on the test box the right-click "Lucky*Star Calculator" still showed "Lucky Star" because
  `C:\lm\Launch.ini` is the hand-written test INI (kept for its `[Data]`/`[Calendar]` config), not the
  patched one — the shipping `out/patched/Launch.ini` carries the `*`. Correct in the build.

---

## 2026-06-22 — Session 11 (calc): the `data.pak` `.nut` LZSS cracked + themed-calculator TL

The last untranslated user-facing surface. `WinCalcImas/Lucky.exe` `DoFileEx` into `calmain.nut`, a
member of `app/calc/data.pak` compressed with the calc's own LZSS (Session-1 left it "deferred / a
different codec"). Cracked it, translated the script strings + the baked button-label PNGs.

### The `.nut` codec (cracked — `mink-format.md` §Compression)
Not the ACZ/Okumura text codec. Derived by hand from 3 back-reference samples, confirmed byte-exact on
all 4 `.nut`: control bits read **MSB-first**, bit **set = literal**; a match token is 2 bytes —
`length=(b0&0x0f)+2` (2..17), `distance=((b0>>4)|(b1<<4))+1` (12-bit window, **overlap-capable**). The
distance's low 4 bits live in `b0`'s HIGH nibble + high 8 in `b1` — a non-contiguous split, which is why
a single-split brute force (LE/BE × one cut point) found nothing; the hand-derivation `(b0>>4)+1 == dist`
on `0xa0/0x60/0x10 → 11/7/2` was the key. Encoder (`pak_compress`) is greedy 3-byte-index longest-match,
self-verifies decode==input before returning, and is even slightly tighter than SYGNAS (9873 vs 9910 B).

### What's where
- `calmain.nut` = the **converter tool** (BPM↔ms, ms↔fps frames, page-count→paper-thickness): `TextBoxStr[0..4]`
  help, note-length result labels (全音符/二分音符/…), paper types (上質紙/アート紙/マット紙), the validation
  msg. **All displayed strings translated to pure ASCII** (DrawTextA → mojibakes on non-JP locale; … -> ...,
  （ms）-> (ms)) and kept within the 176px scrolling textbox. `calculator/calimas/callucky.nut` = comments-only
  (税込/税抜 are PNG buttons, not script) → untouched.
- **Baked button PNGs** (labels rasterised, not runtime-drawn): the 電卓/単位換算 mode tabs, 変換/コピー,
  税+/税-, the ページ数 paper rows. `tools/calc_png.py` erases each glyph run by reconstructing the button
  gradient per-row (median of non-text pixels) and redraws EN in **MS PGothic** (the builder font →
  matches the app). Profiled column-ink to box only ページ数 and keep " -> mm". Owner-tuned via llm-feed:
  all button text size 12; tabs Calc/Convert, 変換->Convert, コピー->Copy, 税+/税- ->Tax+/Tax-, ページ数->pages.

### Tooling + pipeline
- `sygnas_unpack.pak_decompress` + `parse_packdata` now decode `.nut` (was emitted `.raw`).
- `sygnas_repack.pak_compress` + `repack_packdata` + `--selftest-pak` (4 ok, 0 fail).
- `build_patch` new **`pak` op**: per-member `subs` (decode .nut → cp932 find/replace → re-compress;
  asserts every string literal is ASCII after) or `src`; plus `gen="calc_png"` (retext the button PNGs
  from the user's OWN images at build time — never a committed SYGNAS PNG; pillow lazy-imported).
- Verified: the rebuilt `data.pak` changes exactly `calmain.nut` + the 14 button PNGs; the other 100
  members are byte-identical. **Translation surface is now complete** (only the deferred facenames —
  fine when PGothic present, which the installer bundles — + MFC/VERSIONINFO boilerplate + the textless
  `.mink` sprite codec remain). Live-on-XP render check still pending (box was in NixOS this session).

---

## Session 14 (2026-06-23) — MinkIt `.mink` info-codec + gcal.exe event-draw internals

### MinkIt `.mink` `info` codec (the third LZSS — cracked, byte-exact on all 10)
Decompiled `MinkIt.dll`: `GetExtraInfo`@0x10001a70 / `FUN_100018e0`@0x100018e0 read the `info` chunk via
`FUN_10002570`@0x10002570 (mmap the named chunk) → `FUN_100023e0`@0x100023e0 (decoder) → parse `Title=`/
`Author=`/`Pattern=`/`Interval=` keys. The decoder + bit reader `FUN_10002350`@0x10002350:
- chunk = `[u32 decompressed_size][bitstream]`; bits **MSB-first**, cursor walks the whole chunk.
- per token: control bit **0 = literal** (next 8 bits = a byte); **1 = back-ref** (8-bit distance back,
  4-bit length; copied byte-by-byte → overlap/RLE OK). Both fields RAW (no `+threshold`); 256 B window.
- **stops on source-EOF**: `FUN_10002350` returns EOF the moment it *loads* the final chunk byte (never
  consumed) — so a valid stream's tokens end on a byte boundary and the last byte is a throwaway terminator.
  The decoder ignores `decompressed_size` for stopping (only mallocs `size+100` with it).
- Decoded info is the same for a character's `_copy` + `_dl`. `(無題)`/`(不明)` in MinkIt.exe are only the
  Title/Author **fallbacks** (used when a key is absent), NOT — as the old notes said — the always-shown text.
Ported to `tools/sygnas_unpack.mink_info_decompress` + `sygnas_repack.mink_info_compress`/`repack_mink`
(greedy bit-encoder, NUL-literal byte-align + terminator, self-verify). `docs/mink-format.md` updated.

### gcal.exe month-grid event drawing (items 3+4 — one shared root cause)
`CGoogleEvent` Atom parser (~all.c L7240-7345): reads `id`, `title`, `gd:when`, `gd:where`, `gCal:color`,
and **`link[@rel='alternate']/@href`**. The drawer `FUN_00409980`@0x409980 (per-day-cell event list) +
the click hit-test `FUN_004032a0`@0x4032a0:
- each drawn event becomes a 0x34-byte hit object: `*obj=2` (clickable type), `obj+4..+0x10`=rect,
  **`obj+0x14` (=`obj[5]`) = the event's href** (copied from `event+0x1c`, L7679; also L1494-1520 / L3260).
- click (`FUN_004032a0` L1604/L1624): obj type `1` → opens the day-detail dialog; type `2` →
  `ShellExecuteW(0,"open", obj[5], …)` — i.e. **opens the href in the browser**.
- row layout: event Y = `FUN_0040a050(date,event,…) * 0xd + cell_top` (0xd=13 px/row). `FUN_0040a050`
  @0x40a050 assigns the row by matching **`event+0x1c` (the href)** against a per-weekday-column slot table
  (`DAT_0045e114 + col*0x50`, ≤0x14 rows) — a stable unique href keeps a multi-day event on one row across
  columns. `FUN_00408880`@0x408880 is an insertion-sort of the day's events by (start-time, key), not a dedup.
- **Consequence:** our feed gave every event an EMPTY href (no `<link>`/`<id>`) → identical slot key → all
  events collapse to row 0 (the "one line" bug) AND `ShellExecuteW("")` → cwd (the "opens the folder" bug).
  Fixed feed-side by emitting a unique per-event `<id>` + alternate `<link href>` (see `gcalsrv.lua`).
- The day-cell itself also builds a type-2 object whose href is the add-event TEMPLATE
  `http://…/calendar/event?action=TEMPLATE&dates=%4d%02d%02d/%4d%02d%02d` (L1490) — clicking empty day space
  opens "add event". We reuse that same URL shape for the per-event links so one `/calendar/event` handler serves both.
