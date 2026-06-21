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
