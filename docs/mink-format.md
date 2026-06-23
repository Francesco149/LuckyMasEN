# SYGNAS container formats — `MINK` · `ACZ` (.Xvi) · `PACKDATA` (.pak)

Reverse-engineered from the 2007 「らき☆マス」disc (MSVC-2005 native binaries). All three are
**simple little-endian chunk/file directories** — none is the undocumented dead-end the scope doc
feared. Offsets below are verified against the real files in `originals/installed/`.

Status: **directory layouts solved; the ACZ text, PACKDATA `.nut`, and `.mink` `info` codecs are
cracked.** Open: only the `.mink` `a0`/`m0` **sprite** codec (carries no text — doesn't gate the TL).

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
| `info` | 0x40      | 0x60 (96 B) | per-character metadata, LZSS-compressed — see below |
| `a0`   | 0xA0      | ~0x2DD510 (≈3.0 MB) | sprite/atlas stream (codec) |
| `m0`   | 0x2DD5B0  | ~0x1C2A20 (≈1.85 MB)| mask/alpha stream (codec) |

- **`info` IS per-character metadata** (an earlier note here guessed "fixed codec table" — wrong;
  it decompresses to per-character text). It is `[u32 decompressed_size][LZSS bitstream]` in
  MinkIt's own bit codec ([§Compression](#compression--mink-info--a-third-lzss--cracked)). Decoded,
  every `.mink` is a tiny cp932 INI (CRLF-terminated keys):
  ```
  Title=こなた          ← the name shown in the Settings list (control 0x3ec) + Preview "Title:"
  Author=SYGNAS        ← Preview "Author:"
  RefURL=http://sygnas.jp/
  Pattern=118          ← animation frame count
  Interval=33          ← frame interval (ms)
  ```
  Read by `MinkIt.dll!GetExtraInfo` (@0x10001a70): it scans the decoded text for `Title=`/`Author=`
  keys (others ignored) and stores them in a per-`.mink` struct (stride 0x180; Title at +0, Author
  at +0x40). `MinkIt.exe`'s `(無題)`/`(不明)` are only the **fallback** Title/Author (shown if the key
  is absent). The EN patch rewrites `Title=` to ASCII via `build_patch`'s `[[mink_info]]` op
  (`tools/sygnas_repack.py:repack_mink`), leaving a0/m0 byte-identical.
- **`a0` and `m0` both begin** `38 47 03 01 21 13 47 04 70 18 04 01 01 31 b4 10` — identical across
  characters *and* across `_copy`/`_dl`. → a **common stream header** for the sprite codec. The
  payload is **not plain SJIS/PNG/BMP** (a text scan yields only high-entropy false positives) →
  it is **compressed or encrypted**. Cracking this sprite codec is the one hard RE task left; the
  loader is `MinkIt.dll` (start there in Ghidra — it has the only code that touches these bytes).
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

→ The launcher's PNGs come straight out (stored, 8-bit RGBA). The **`Ini` blob decompresses (LZSS,
below) to the character's speech config** — `[NAME] Name=…`, `[POS]` (sprite + speech-bubble layout:
`Center`, `Bust{X,Y,W,H}`, `Serif{X,Y}`), and `[Msg]` with **10 `Serif*` dialogue lines**
(`SerifNewVersion`, `SerifMailCheck`, `SerifCallenderSchedule=今日の予定は\n<%SCHEDULE%>…`, …, with
`\n` line breaks + `<%VAR%>` templates). `tools/sygnas_unpack.py` extracts all **22 characters'
name + 220 speech lines** as editable Shift-JIS INI — the launcher's entire text surface.

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
  — **compressed** with the calc LZSS (stored 0x8BB < uncomp 0x2056; ✅ cracked, see [§Compression](#compression--packdata-nut--a-second-lzss--cracked)).
  `calmain.nut` carries the converter's display strings → translated. The button LABELS are baked
  into the `.png` skins (the 電卓/単位換算 tabs, 変換/コピー, 税+/税-, ページ数) → retexted by
  `tools/calc_png.py` (build_patch `[[pak]] gen`).

---

## Compression — ACZ text = Okumura LZSS (✅ confirmed)

The ACZ `Ini` blob is **canonical Okumura LZSS**, proven by byte-exact decode of all 22 launcher
files (`tools/sygnas_unpack.py`): ring buffer **N=4096**, max match **F=18**, **THRESHOLD=2**, ring
**pre-filled with `0x20`**, flag bit **set = literal** (clear = a 2-byte back-reference:
`pos = lo | ((hi & 0xF0) << 4)`, `len = (hi & 0x0F) + 3`). The leading **`0xFF`** everyone notices is
simply the **first flag byte** — the opening 8 tokens are all literals because the ring is still
"empty", so it's not a separate marker. Each `Ini` decodes to exactly its recorded `usize`, clean Shift-JIS.

## Compression — PACKDATA `.nut` = a second LZSS (✅ cracked)

The calc `data.pak` `*.nut` (Squirrel) use a **different LZSS** from the ACZ text codec — same
"`0xFF` = first all-literal flag byte" opening, but the bits are read **MSB-first** and the
back-reference is packed differently. Byte-exact on all four `.nut` (`tools/sygnas_unpack.pak_decompress`;
encoder `tools/sygnas_repack.pak_compress`):
- a control byte's 8 bits are consumed **MSB-first**; bit **set = literal** (one byte),
  bit **clear = a 2-byte match token** `(b0, b1)`:
  - `length   = (b0 & 0x0F) + 2`           (2..17)
  - `distance = ((b0 >> 4) | (b1 << 4)) + 1`  (1..4096 — a 12-bit window; the low 4 distance bits sit
    in `b0`'s **high** nibble, the high 8 in `b1`, which is why a single contiguous bit-split misses it)
  - the copy is **overlap-capable** (RLE: `length` may exceed `distance`).

`calmain.nut` holds the converter tool's display strings (note-length / fps / paper-thickness) →
translated to ASCII via build_patch's `[[pak]]` op; `calculator/calimas/callucky.nut` are comments-only.

## Compression — `.mink` `info` = a third LZSS (✅ cracked)

The `.mink` `info` chunk uses **MinkIt's own** bit-oriented LZSS — distinct again from the ACZ and
PACKDATA codecs. Ported byte-exact from `MinkIt.dll` (`FUN_100023e0` decoder + `FUN_10002350` bit
reader) and round-trips all 10 `.mink` (`tools/sygnas_unpack.mink_info_decompress` /
`tools/sygnas_repack.mink_info_compress`):
- Chunk = `[u32 decompressed_size][bitstream]`. Bits are pulled **MSB-first** within each byte and
  the byte cursor advances across the whole chunk.
- Each **token** starts with a 1-bit control flag:
  - **`0` = literal** — the next **8 bits** are one output byte.
  - **`1` = back-reference** — **8 bits = distance** (1..255, bytes back from the current output
    position) then **4 bits = length** (copied byte-by-byte, so overlap/RLE is allowed). Note both
    fields are raw (no `+threshold` bias), and the window is only 256 B — fine, the chunks are ~80 B.
- **Termination is by source-EOF, not a count:** the bit reader returns EOF the instant it *loads*
  the final chunk byte (that byte is never consumed), so a valid stream's tokens end exactly on a
  byte boundary and the last byte is a throwaway terminator. The decoder does not use
  `decompressed_size` to stop (it sizes the output buffer with it). Our encoder reproduces this:
  greedy match, then pad to a whole byte with NUL-literals (which decode to NULs that also
  NUL-terminate the engine's text scan), then append one terminator byte.

The decoded text is the per-character metadata documented in [§MINK](#mink--appcopymink-mascot-copydownload-animations);
the EN patch retitles it via `[[mink_info]]` (`tools/build_patch.py`).

Still open — **`.mink` `a0`/`m0`** (sprite + mask): Okumura yields a run of `0x20` (ring-init
leakage) → **not** that codec; a separate sprite stream (`38 47 03 01 21 13 47 04 …`, header
identical across all files). Carries no translatable text → deferred (a sprite-editing nicety;
doesn't gate the TL). **To crack it:** decompile the decode routine in `MinkIt.dll` (MSVC-2005,
unstripped, cdecl) in Ghidra.

## Tooling

`tools/sygnas_unpack.py` + `tools/sygnas_repack.py` round-trip all three text/metadata codecs
(ACZ `Ini`, PACKDATA `.nut`, MINK `info`) byte-exact; `build_patch.py` drives the translation via
the `xvi`/`pak`/`mink_info` ops. Self-tests: `--selftest <dir-of-.Xvi>`, `--selftest-pak <data.pak>`,
`--selftest-mink '<glob-of-.mink>'` each prove encode∘decode == identity on the user's own originals.
Only the `.mink` `a0`/`m0` **sprite** codec remains un-round-tripped (stored verbatim; carries no text).
