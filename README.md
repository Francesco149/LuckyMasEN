# LuckyMasterEN

English fan-translation **patch + tooling** for SYGNAS 「らき☆マス」(*Lucky☆Mas*) — a 2007
*Lucky☆Star × THE iDOLM@STER* doujin desktop-accessory pack (circle **SYGNAS**, catalog
SGNS-0009, Comiket 73) — and a reverse-engineering log for its in-house **MinkIt** mascot engine.

Companion to the [`retro-hardware`](../retro-hardware) Time Machine (Windows XP) build. The full
project scope, owner constraints, research findings, and approach analysis live upstream in
**`retro-hardware/projects/minkit-en-patch/README.md`** — read that first. This repo is where the
actual RE notes, format specs, tooling, and the redistributable patch are built.

## The English installer — the deliverable

![Lucky*Mas English installer: the faithful 586×364 wizard with bundled MS PGothic, on an XP with no East-Asian language pack](docs/screenshots/installer-wizard-faithful-586x364.png)

An English re-wrap of SYGNAS's own Inno Setup wizard — the original's full-screen blue gradient, Lucky☆Star
art, and pixel-exact **586×364** size — recompiled from the user's *own* `setup.exe` (never redistributing a
SYGNAS byte). That faithful size is MS PGothic's specific metrics; no Latin font reproduces it, so the
toolchain bundles a **builder-supplied** copy of the font ([`tools/get_font.py`](tools/get_font.py) →
`installer/setup.iss`), `AddFontResource`-d for the wizard and installed for the app's serifs — rendering
correctly even on an XP with no East-Asian fonts (shown above, validated on the q9650 test box).

## Demo — the mascots run their own calendar, no Google account

| `SerifCallenderSchedule` — today's events | `SerifCallenderNone` — empty calendar |
|:---:|:---:|
| ![today's schedule bubble](docs/screenshots/gcal-schedule-bubble.png) | ![no plans bubble](docs/screenshots/gcal-none-bubble.png) |

Hiyori on real **Windows XP SP3**, reading her calendar from our **native XP-local fake-Google server**
([`tools/gcal-xp/`](tools/gcal-xp/README.md)) — a single ~300 KB Win32 EXE that answers as
`www.google.com` over the box's own 2007 **WinINet↔Schannel** TLS stack (Schannel ClientLogin + GData
feeds + POP3; request logic in embedded Lua). The events (*Dentist / Lunch with Konata / Buy doujinshi*)
are served entirely **locally** and the speech bubbles are in our English translation — no Google
account, no internet.

## Hard rule: no redistribution of original files

We ship **only a delta + a tool** that applies to the user's *own* copy of the disc. No SYGNAS
file is ever committed or distributed. The owner's working copy lives in `originals/` and is
**gitignored** (see [`originals/README.md`](originals/README.md)).

## Goals

1. **English-patch** the Win32 GUI and any translatable in-`.mink` / sub-app text.
2. **Kill the JP-locale dependency** — patch the hardcoded non-Latin paths (`らき―copy`,
   `かがみ_copy.mink`, …) so it runs on a non-JP locale **without** AppLocale / full-system JP locale.
3. Reverse-engineer and document the undocumented **`.mink`** container format.
4. (Stretch) fix the known **mouse-hover hit-region offset** bug.

Deliverable is either **(A)** a runtime hot-patch launcher (hooks ANSI text + file APIs; never
mutates originals) or **(B)** a static patcher that emits an xdelta3/IPS delta — decided after the
first RE pass (both need the same recon).

## Layout

| Path | What |
|---|---|
| `flake.nix` | the whole toolchain — `nix develop` (ghidra, rizin/cutter, wrestool, pev, imhex, wine, qemu, xdelta3, python+construct/lief/pillow) |
| `docs/` | RE log (`re-notes.md`), the `mink-format.md` spec, and `patch-system.md` (the reproducible patch) |
| `tools/` | extractors + the patch engine `build_patch.py` + the native server `gcal-xp/` (the redistributable tooling) |
| `patch/` | the patch sources + **`manifest.toml`** — the single source of truth for every file we patch |
| `out/` | **gitignored** — the built patched English tree (`build_patch.py` output) + `PATCH-LOG.txt` |
| `originals/` | **gitignored** — owner's own RE input (disc rip + cracked installer payload) |

## Quick start

```sh
nix develop          # drops into the RE/TL shell with every tool on PATH
```

## Status

Bootstrapping. See `docs/re-notes.md` for the running RE log and the upstream scope doc for the
plan.
