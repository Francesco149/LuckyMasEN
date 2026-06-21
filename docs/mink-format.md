# SYGNAS container formats — `MINK` · `ACZ` (.Xvi) · `PACKDATA` (.pak)

Reverse-engineered from the 2007 「らき☆マス」disc (MSVC-2005 native binaries). All three are
**simple little-endian chunk/file directories** — none is the undocumented dead-end the scope doc
feared. Offsets below are verified against the real files in `originals/installed/`.

Status: **directory layouts solved.** Open: the per-blob **codec** (see [§Compression](#compression)).

---

## `MINK` — `app/copy/*.mink` (mascot "copy/download" animations)

The MinkIt engine's character containers (`<char>_copy.mink`, `<char>_dl.mink`; 10 files, ~4.8 MB each).

```
off   size  field
0x00  4     magic  "MINK"
0x04  4     version (u32)         — varies per file: seen 1 (かがみ_copy) and 3 (こなた_dl); meaning TBD
0x08  4     chunk count (u32)     — observed 3
0x0C  4     reserved (0)
0x10  …     chunk directory: count × 16-byte records:
              +0x00  8  name  (NUL-padded ASCII)  — "info", "a0", "m0"
              +0x08  4  offset (u32, absolute from file start)
              +0x0C  4  size   (u32)
```

Chunks (かがみ_copy.mink):

| name   | off       | size        | what |
|--------|-----------|-------------|------|
| `info` | 0x40      | 0x60 (96 B) | fixed header — see below |
| `a0`   | 0xA0      | ~0x2DD510 (≈3.0 MB) | sprite/atlas stream (codec) |
| `m0`   | 0x2DD5B0  | ~0x1C2A20 (≈1.85 MB)| mask/alpha stream (codec) |

- **`info` is NOT per-character metadata.** Its first 0x40 bytes are *byte-identical* between
  different characters (かがみ vs こなた): `51 00 00 00 2a 1a 4e 86 c3 28 f5 04 …`. → a **fixed
  codec/key table or dictionary**, shared by all `.mink`. (High-entropy after the first u32.)
- **`a0` and `m0` both begin** `38 47 03 01 21 13 47 04 70 18 04 01 01 31 b4 10` — identical across
  characters *and* across `_copy`/`_dl`. → a **common stream header** for the sprite codec. The
  payload is **not plain SJIS/PNG/BMP** (a text scan yields only high-entropy false positives) →
  it is **compressed or encrypted**. Cracking this codec is the one hard RE task left; the loader is
  `MinkIt.dll` (start there in Ghidra — it has the only code that touches these bytes).
- Naming guess: `a0` = animation/atlas 0, `m0` = mask 0 (per-pixel transparency for the layered window).

---

## `ACZ` — `app/launcher/*.Xvi` (launcher character assets, 23 files)

```
off   size  field
0x00  4     magic  "ACZ\0"
0x04  4     (0)
0x08  4     entry count (u32)     — konata.Xvi = 3
0x0C  4     (0)
0x10  …     directory: count × 32-byte records:
              +0x00  16  name (NUL-padded ASCII) — "CharaMain00", "CharaMain01", "Ini"
              +0x10  4   offset (u32, absolute)
              +0x14  4   stored size   (on-disk bytes; gap-verified)
              +0x18  4   uncompressed size
              +0x1C  4   tag — low byte 0x00=stored / 0x01=compressed (hypothesis); high 3 bytes look like a checksum
```

konata.Xvi entries:

| name | off | stored | uncomp | head | what |
|------|-----|--------|--------|------|------|
| `CharaMain00` | 0x70    | 0x19C24 | 0x19C24 | `89 50 4E 47` = **PNG** | character frame 0 (stored, sizes equal) |
| `CharaMain01` | 0x19C94 | 0x197AC | 0x197AC | **PNG** | character frame 1 |
| `Ini`         | 0x33440 | 0x262   | 0x390   | `FF 5B 4E 41 4D 45 5D` = `\xFF[NAME]` | **compressed text** config/speech |

→ The launcher's PNGs come straight out (stored). The **`Ini` blob is compressed text** (`[NAME]…`)
— almost certainly the character's name/dialogue (cf. `Launch.exe`'s `SERIF_BASE` speech bitmap and
its `TextOutA`/`DrawTextA`). **Translatable once the codec is cracked.**

---

## `PACKDATA` — `app/calc/data.pak` (calculator assets)

```
off   size  field
0x00  8     magic  "PACKDATA"
0x08  4     file count (u32)      — 115
0x0C  4     (0)
0x10  …     directory: count × 44-byte records:
              +0x00  32  name (NUL-padded ASCII) — "base.png", "calculator.nut", …
              +0x20  4   uncompressed size
              +0x24  4   stored size  (on-disk; gap-verified)
              +0x28  4   offset (u32, relative to the data section)
   data section starts immediately after the directory: 0x10 + count*44  (= 0x13D4 for 115 files)
```

Contents histogram: **111 × `.png` + 4 × `.nut`**.
- PNGs: stored uncompressed (uncomp == stored).
- **`*.nut` = Squirrel scripts** (`calculator.nut` head `FF 2F 2A 20 8C 76 8E 5A` = `\xFF` + `/* 計算`)
  — **compressed** (stored 0x8BB < uncomp 0x2056). The calculator's logic *and its display strings*
  live here → a prime translation target once decompressed.

---

## Compression

A recurring scheme on the **text-bearing** blobs (ACZ `Ini`, PACKDATA `*.nut`): a leading **`0xFF`**
byte, then a stream whose start *looks* like the plain text (`[NAME]`, `/* 計算`) but whose stored
length is < the recorded uncompressed length. → a lightweight **LZ/RLE with `0xFF` as the opcode/escape**
(SYGNAS in-house, shared lib). PNG chunks are stored verbatim (no `0xFF`, sizes equal). The `.mink`
`a0`/`m0` streams use a *different* framing (`38 47 03 01…`, no `0xFF` lead) — possibly the same
codec with a different header, possibly heavier/encrypted.

**To finish:** decompress one ACZ `Ini` (smallest, plain-text target) → infer the opcode set →
apply to `.nut` → then attack the `.mink` `a0`/`m0`. Decompiling the relevant routine in `MinkIt.dll`
/ `Launch.exe` (both MSVC-2005, unstripped, cdecl) in Ghidra is the reliable path.

## Tooling

`tools/` will grow an unpacker/repacker per format (Python + `construct`; the directory math above is
enough to round-trip the **stored** chunks today). The codec is the gate for the compressed chunks.
