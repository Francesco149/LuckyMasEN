# The screensavers — teardown of a cursed engine

The disc's four screensavers (`sys/*.scr`) **do not work, and never did from the disc** — and contrary
to the long-standing assumption, it has **nothing to do with locale, our rename, or the Flash version**.
This is the full reverse-engineering story and the live proof.

## TL;DR

- The four `.scr` are **byte-identical** — one binary, **ScreenTime For Flash** (commercial; "ScreenTime
  Screensaver Engine", © ScreenTime Media 1995-2006), shipped under four filenames.
- A *working* ScreenTime screensaver = the engine `.scr` **plus** a **`saver.dat`** content package (which
  holds the actual Flash movie) **plus** the **Flash Player 8** ActiveX control.
- **The disc shipped only the engine `.scr`.** No `saver.dat`, no movie, no Flash. So on launch the engine
  looks for `saver.dat`, doesn't find it, sets an error flag, and **exits before it ever creates the Flash
  control** — in ~2 s. In Display-Properties *preview* (`/p`) it shows a Japanese error
  (「…再起動してください」, drawn by the engine path, not in the binary's plaintext); run full (`/s`) it just
  exits.
- This is a **SYGNAS packaging defect**, independent of locale / filename / system date — proven by
  decompilation *and* live testing.
- SYGNAS knew: they later released the **working** versions on their (now-defunct) website **as an apology**
  — standalone installers that bundle the movie + Flash 8. Installing one over the disc stub yields a
  working screensaver (verified live).

## What it is

`rz-bin`/Ghidra on the unpacked binary: an MFC app, ASPack-packed (`.aspack`/`.adata` sections, non-exec
`.text`). Tell-tale strings: `ScreenTime Screensaver Engine`, `Made with ScreenTime for Flash.`,
`ssPlayer.dat`, `\saver.dat`, `\saver.swf`, `\saver1.dll`, `\expire.scf`, `CShockwaveFlash`, the Flash
ActiveX CLSID `{D27CDB6E-AE6D-11cf-96B8-444553540000}`, and FSCommand verbs the movie can call
(`downloadFile`, `loadRemoteFile`, `checkNetConnection`, `wallpaper`). It plays a Flash movie via the Flash
ActiveX; the per-name "different content" idea from earlier notes is moot (see below).

## How it was taken apart

1. **Unpack the ASPack stub.** No unicorn/aspackdie in the shell, so a from-scratch **Unicorn emulator**:
   [`work/scr/unpack.py`](../work/scr/unpack.py) maps the PE, gives the stub a fake kernel32
   (`GetProcAddress` hands back real trampolines for the funcs the stub calls — `VirtualAlloc`/`Protect`),
   sets FS via a GDT, and uses the **ESP trick** (watch the outer `popad` restore the entry `pushad` frame)
   to stop at the true OEP (`0x42eae4`) — *after* full decompression, *before* the original code runs. Dumps
   a flat image; a header-fixup makes a "flat PE" (`PointerToRawData == VirtualAddress`) so tools map it 1:1.
2. **Decompile.** Ghidra headless → all 2445 functions (`out/ghidra/scr/`, gitignored). `work/scr/screscan.py`
   annotates IAT calls.
3. **Find the exit.** The init `FUN_00401871` parses the mode (`/s /p /c /a /x /u`), builds a working dir
   from `GetWindowsDirectory`/`GetSystemDirectory`, then:
   `path = workdir + "\saver.dat"; if (!exists(path)) error_flag = 1;` — and with the flag set it skips the
   whole play path and returns 0. `saver.dat` is only ever **read**, never written → it must pre-exist.

## The evidence it's not locale / name / date

Live on real XP (an EN-locale box and a JP-locale box):

| variant | result |
|---|---|
| English-locale XP | dies in ~2 s |
| Japanese-locale XP | dies in ~2 s |
| English-renamed `.scr` (both boxes) | dies |
| Japanese-named `.scr` (both boxes) | dies |
| system clock rolled back to **2007** | still dies (so not a date/expiry check) |
| stock `ssstars.scr` launched the same way (control) | **runs fine** |

After a run the engine's `ping.txt` connectivity marker appears, but **`saver.dat` never exists anywhere**
(whole-`C:` search). And the disc genuinely never had it: `innoextract -l` of the disc `setup.exe`
(SHA-256 `f3940514…`) lists 164 files in `app/` + `sys/` only — **zero `.dat`**; the ~135 KB packed engine
has no room to embed a movie.

## Why the disc only has stubs

Documented creator history (community, 2026): the disc screensavers *"had errors that just made them flat
out not work,"* so SYGNAS released the **true working ones on their website as an apology/compensation.**
Those are standalone installers — `chibi_setup.exe`, `imas3d_setup.exe`, `imas_comic_setup.exe`,
`luckystar_comic_setup.exe` — that bundle the engine + a **Flash-8 movie** (`CWS v8`: chibi ≈ 162 KB,
imas3d ≈ 14.5 MB) + **`flash8.ocx`** (Flash Player 8 ActiveX). The disc bundled only the gutted engine.

**Verified live:** installing `chibi_setup.exe` over the broken stub → the chibi screensaver previews in
Display Properties **and** runs fullscreen (iM@S/Lucky☆Star chibis on coloured stripes).

## Restoring them — DONE (`tools/screensaver_restore.py`)

The EN build now restores the working screensavers by extract-and-merge from SYGNAS's apology installers
(the content was never on the disc, so it comes from outside): the four are pinned on **archive.org**
(`archive.org/details/lucky-mas-screensavers`) by SHA-256 (zip + inner `setup.exe`), downloaded at build,
**never committed** (the hard rule). What we learned tearing the installers apart (full RE: an
InstallShield-MSI wrapping `[IS stub | Flash-8 MSI | tail payload]`; the InstallScript front-end, not the
`/s` flags, drove the GUI, so the silent attempt still popped a wizard — driven headless on Xvfb to capture
ground truth):

- **The engine `.scr` is byte-identical to the disc's** (sha `6b430059…`, 203264 B, one binary × 4 names).
  So the patch *already ships the working engine* — restore adds only the missing content.
- A working install = `{sys}\<Name>.scr` **+** `{sys}\<Name> dir\` holding `saver.dat` (a 1240-B
  descriptor), the Flash movie, `saver1.dll`/`saver2.dll`, and `expire.scf`/`prevmon.scf`/`setwnd.scf`
  (FWS/BMP assets) **+** `{sys}\Macromed\Flash\Flash8.ocx` (registered). The engine derives its working
  dir as **`<own-.scr-basename> dir`** (proven live: renaming the `.scr`+dir to English Just Works).
- `saver.dat`'s 6 install-time bytes at 388..397 are runtime state — zero is fine (proven). `saver.dat`
  names the movie in a NUL-terminated field at **offset 312**, opened via the ANSI API → a cp932 name
  fails on EN-locale XP, so we rename the movie to `saver.swf` and rewrite that field ASCII (goal #2).
- Every payload file sits **verbatim and contiguous** in the apology installer → carved by (offset,size),
  each SHA-256-verified (the parent installer is itself pinned — same idea as the `asmpoke` ops).
  `Flash8.ocx` is **LZX**-compressed in the MSI's `Data1.cab`, itself an OLE-compound-document *stream*
  (fragmented across FAT sectors) → reassembled with a minimal pure-Python CFB reader, then unpacked with
  `cabextract`/`7z`/Windows `expand`.

`make_iso.py` runs the restore after the patch (non-fatal; `--skip-screensavers` to opt out); `setup.iss`
ships the working dirs + Flash and `regsvr32`-registers the OCX (both `#if FileExists`-guarded).

**What each one shows** (all four are the SYGNAS Flash content, unchanged — only filenames are ASCII'd):
- **Chibi Characters** — 2D chibi mascots walk across the screen leaving coloured trails.
- **iM@S 3D** — a busy 3D scene: iDOLM@STER idols walking and crossing paths (765Pro angel watermark).
- **iM@S 4-koma / Lucky☆Star 4-koma** — slowly play a cutscene told in manga panels (they fade to white
  between panels — mind that when screenshotting).

**Validated end-to-end under wine** (built EN installer → silent install → all four run fullscreen) **and
LIVE on the real EN-locale box q9650** (wiped prior install → installed the built `setup.exe` → all four
preview/run fullscreen; the ASCII swf/`saver.dat` fix confirmed on actual EN XP, not just wine). The
clean-install ops are scripted in retro-hardware `projects/minkit-en-patch/clean-deploy-xp.sh`. RE tooling
+ the per-installer extraction table: `tools/screensaver_restore.py`; session log in
[`next-builds.md`](next-builds.md) §"Session 18".

## Ops note (gotcha)

Rolling an XP box's clock far from the present **breaks `smbclient`'s NTLM auth** (`NT_STATUS_LOGON_FAILURE`)
— but **`netexec`/`atexec` is immune**, so use it to set the clock back and recover.
