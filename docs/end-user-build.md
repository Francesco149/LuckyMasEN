# Build your own English Lucky\*Mas disc

This toolchain turns **your own** SYGNAS 「らき☆マス」 disc into an **English** one. You run a
single command; out comes `LuckyMas-EN.iso` (a drop-in English replacement disc image) plus a
`LuckyMas-EN.zip` (just the English `setup.exe`, if you'd rather not burn/mount an ISO).

Nothing here redistributes a SYGNAS file or the Microsoft font — you supply both from your own
licensed copies, exactly like any fan-translation patch. The tool only ships the *delta* + the
machinery that applies it.

## What you need

1. **Your disc's `setup.exe`** — the only file taken from your SYGNAS disc. (No need to install the
   game first; the tool reads the app straight out of `setup.exe`.)
2. **MS PGothic (`msgothic.ttc`)** — a Microsoft font you're licensed to via your own Windows / XP
   CD. On Windows/WSL the tool finds it automatically (`--font auto`). Other sources:
   `python tools/get_font.py --list-sources`.

The faithful 586×364 wizard and the mascots' speech-bubble font both come from MS PGothic, so the
build needs it; it gets bundled into *your* `setup.exe` and installed on the XP box.

---

## Windows — zero install

1. Download **`LuckyMasEN-builder-win.zip`** and unzip it anywhere.
2. Open a Command Prompt in that folder (Shift-right-click → *Open command window here*), and run:

   ```bat
   build.bat --setup D:\setup.exe --font auto
   ```

   Replace `D:\setup.exe` with the path to your disc's `setup.exe` (a drive letter, or a copy on disk).
3. Out comes **`out\LuckyMas-EN.iso`** (+ `out\LuckyMas-EN.zip`). Burn or mount the ISO on your XP box
   and run `setup.exe`, or just unzip the `.zip` and run `setup.exe`.

`build.bat` runs the Inno Setup compiler and innounp **natively** (no wine, no Docker). On the first
run it fetches a private Python into `.\python` and a couple of packages — so it needs internet once;
after that it works offline. (The Inno Setup compiler / innounp / innoextract are already in `.\cache`.)

---

## Linux — Nix (one command)

```sh
git clone https://github.com/Francesco149/LuckyMasEN && cd LuckyMasEN
nix run .#iso -- --setup ~/setup.exe --font auto
```

or without cloning first:

```sh
nix run github:Francesco149/LuckyMasEN#iso -- --setup ~/setup.exe --font auto
```

The flake brings every tool (innoextract, wine for ISCC/innounp, xorriso); the Inno Setup compiler
and innounp are auto-downloaded (pinned + SHA-256) into `~/.cache/luckymasen`. Output lands in `./out/`.

## Linux — without Nix

Install: `python3` (with `pillow`, `lief`, `pycdlib`), `innoextract`, and `wine`. Then:

```sh
python3 tools/make_iso.py --setup ~/setup.exe --font auto
```

`make_iso.py` auto-downloads the Inno Setup compiler + innounp (pinned + verified) and runs them
under wine; the ISO is written with `pycdlib` (or `xorriso`/`genisoimage` if present).

---

## Options (`make_iso.py` / `build.bat`)

| flag | meaning |
|---|---|
| `--setup PATH` | your disc's `setup.exe` (**required**) |
| `--font auto\|PATH` | `auto` = find MS PGothic on Windows/WSL; or a `msgothic.ttc`; or an XP `.iso` |
| `--out DIR` | output directory (default `out/`) |
| `--name NAME` | basename for the `.iso`/`.zip` (default `LuckyMas-EN`) |
| `--iscc / --innounp / --innoextract PATH` | use a tool you already have instead of auto-fetching |
| `--offline` | never download — use only cached/`PATH` tools |
| `--no-iso` | stop after the English `setup.exe` (skip the ISO/ZIP) |

## How it works (and what's whose)

```
your setup.exe ─innoextract→ app tree ─build_patch→ English tree ┐
your MS PGothic ─get_font→ msgothic.ttc                          ├─ISCC→ English setup.exe ─→ ISO + ZIP
your setup.exe ─innounp→ Lucky☆Star wizard art                  ┘
```

Everything except your `setup.exe` and your `msgothic.ttc` is part of this open toolchain (the patch
in `patch/`, the installer script in `installer/`, the native fake-Google calendar server
`tools/gcal-xp/gcalsrv.exe`). The build output contains SYGNAS bytes, so keep your `LuckyMas-EN.iso`
to yourself — share only the disc you started from with people who own it.

## Auto-downloaded build tools (pinned + checksummed)

| tool | version | why |
|---|---|---|
| Inno Setup compiler (ISCC) | 5.6.1 | compile the English installer |
| innounp | 0.50 | extract the faithful wizard art from your `setup.exe` |
| innoextract | 1.9 | read the app tree out of your `setup.exe` (Linux: from your distro/nix) |

## Troubleshooting

- **“could not auto-locate MS PGothic.”** Pass it: `--font C:\Windows\Fonts\msgothic.ttc` (Windows)
  or `--font /path/to/msgothic.ttc`, or point at an XP CD/ISO: `--font D:\xpcd.iso`.
- **No internet on the build machine.** Pre-populate the cache (or use the Windows bundle, whose
  `cache\` is pre-seeded) and pass `--offline`.
- **It says `gcalsrv.exe not found`.** Use a release bundle (it's included), or build it once with
  `tools/gcal-xp/build.sh` (Linux + the mingw cross-compiler; the nix flake does this for you).
