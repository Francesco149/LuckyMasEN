# LuckyMasterEN

English fan-translation **patch + tooling** for SYGNAS 「らき☆マス」(*Lucky☆Mas*) — a 2007
*Lucky☆Star × THE iDOLM@STER* doujin desktop-accessory pack (circle **SYGNAS**, catalog
SGNS-0009, Comiket 73) — and a reverse-engineering log for its in-house **MinkIt** mascot engine.

Companion to the [`retro-hardware`](../retro-hardware) Time Machine (Windows XP) build. The full
project scope, owner constraints, research findings, and approach analysis live upstream in
**`retro-hardware/projects/minkit-en-patch/README.md`** — read that first. This repo is where the
actual RE notes, format specs, tooling, and the redistributable patch are built.

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
| `docs/` | RE log (`re-notes.md`) + the reverse-engineered `mink-format.md` spec |
| `tools/` | our extractors / patcher / launcher (the redistributable tooling) |
| `patch/` | the translation data (string tables) + generated patch delta |
| `originals/` | **gitignored** — owner's own RE input (disc rip + cracked installer payload) |

## Quick start

```sh
nix develop          # drops into the RE/TL shell with every tool on PATH
```

## Status

Bootstrapping. See `docs/re-notes.md` for the running RE log and the upstream scope doc for the
plan.
