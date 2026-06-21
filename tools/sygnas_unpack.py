#!/usr/bin/env python3
"""
sygnas_unpack.py — unpacker for the SYGNAS 「らき☆マス」(2007) container formats.

Handles the three chunk formats reverse-engineered in docs/mink-format.md:
  MINK     (*.mink)  — mascot copy/download animations  (chunks: info, a0, m0)
  ACZ      (*.Xvi)   — launcher character assets          (CharaMainNN PNGs + an Ini)
  PACKDATA (*.pak)   — calculator assets                  (PNGs + Squirrel *.nut)

Compression: the launcher's ACZ text blob (the `Ini` chunk = the character's
speech/dialogue) uses canonical **Okumura LZSS** (N=4096, F=18, THRESHOLD=2, ring
pre-filled with 0x20, flag bit set = literal). This module decompresses those.
The calc `.nut` blobs and the `.mink` a0/m0 sprite streams use *other* codecs
(not yet cracked) and are emitted raw, with a `.raw` suffix.

Stdlib only — runs anywhere (no flake needed). Reversible; reads originals, never writes them.

Usage:
  sygnas_unpack.py <file.Xvi|.mink|.pak> [outdir]      # one container
  sygnas_unpack.py --dir <indir> <outdir>              # every container under indir
"""
import os, sys, struct

def u32(b, o): return struct.unpack_from('<I', b, o)[0]

def sniff_ext(d):
    if d[:8] == b'\x89PNG\r\n\x1a\n': return '.png'
    if d[:2] == b'BM':                return '.bmp'
    if d[:3] == b'GIF':               return '.gif'
    if d[:3] == b'\xff\xd8\xff':      return '.jpg'
    return '.bin'

# ---- Okumura LZSS (the launcher/ACZ text codec) --------------------------------
def lzss_decompress(data, expected=None, N=4096, F=18, THRESHOLD=2, init=0x20):
    out = bytearray(); ring = bytearray([init]) * N; r = N - F; i = 0; flags = 0
    while i < len(data):
        if expected is not None and len(out) >= expected:
            break
        flags >>= 1
        if (flags & 0x100) == 0:
            if i >= len(data): break
            flags = data[i] | 0xff00; i += 1
        if flags & 1:                                  # literal
            if i >= len(data): break
            c = data[i]; i += 1
            out.append(c); ring[r] = c; r = (r + 1) % N
        else:                                          # (offset,length) back-reference
            if i + 1 >= len(data): break
            lo, hi = data[i], data[i + 1]; i += 2
            pos = lo | ((hi & 0xf0) << 4)
            length = (hi & 0x0f) + THRESHOLD + 1
            for k in range(length):
                c = ring[(pos + k) % N]
                out.append(c); ring[r] = c; r = (r + 1) % N
    return bytes(out)

# ---- container parsers: each yields (name, data, kind) --------------------------
# kind: 'text' = decoded UTF-able config | 'asset' = ready file (PNG/…) | 'raw' = unknown codec
def parse_mink(b):
    assert b[:4] == b'MINK'
    for k in range(u32(b, 8)):
        o = 16 + k * 16
        name = b[o:o+8].split(b'\x00')[0].decode('latin1')
        off, size = u32(b, o+8), u32(b, o+12)
        yield (name, b[off:off+size], 'raw')           # info/a0/m0 codec unknown -> raw

def parse_acz(b):
    assert b[:4] == b'ACZ\x00'
    for k in range(u32(b, 8)):
        o = 16 + k * 32
        name = b[o:o+16].split(b'\x00')[0].decode('latin1')
        off, stored, usize, tag = u32(b, o+16), u32(b, o+20), u32(b, o+24), u32(b, o+28)
        raw = b[off:off+stored]
        if tag & 1:                                    # low bit set = LZSS-compressed
            yield (name, lzss_decompress(raw, expected=usize), 'text')
        else:
            yield (name, raw, 'asset')

def parse_packdata(b):
    assert b[:8] == b'PACKDATA'
    n = u32(b, 8); ents = []; o = 16
    for k in range(n):
        name = b[o:o+32].split(b'\x00')[0].decode('latin1')
        usize, stored, off = u32(b, o+32), u32(b, o+36), u32(b, o+40)
        ents.append((name, usize, stored, off)); o += 44
    ds = o
    for name, usize, stored, off in ents:
        raw = b[ds+off: ds+off+stored]
        yield (name, raw, 'raw' if stored != usize else 'asset')   # PNG 1:1; .nut compressed (codec TBD)

MAGIC = {b'MINK': parse_mink, b'ACZ\x00': parse_acz, b'PACKDATA': parse_packdata}

def out_name(name, data, kind):
    base = name.rsplit('.', 1)[0] if '.' in name else name
    if kind == 'text': return base + '.ini'
    if kind == 'raw':  return name + '.raw' if '.' in name else name + '.raw'
    return name if '.' in name else name + sniff_ext(data)   # 'asset'

def unpack_one(path, outdir):
    b = open(path, 'rb').read()
    parser = next((p for m, p in MAGIC.items() if b.startswith(m)), None)
    if parser is None:
        print(f"  ?? {os.path.basename(path)}: unknown magic {b[:8]!r}"); return
    os.makedirs(outdir, exist_ok=True)
    n = 0
    for name, data, kind in parser(b):
        with open(os.path.join(outdir, out_name(name, data, kind)), 'wb') as f:
            f.write(data)
        n += 1
    print(f"  ok {os.path.basename(path):<18} -> {outdir}  ({n} chunks)")

def main(argv):
    if len(argv) >= 3 and argv[0] == '--dir':
        indir, outroot = argv[1], argv[2]
        for root, _, files in os.walk(indir):
            for fn in sorted(files):
                if fn.lower().endswith(('.xvi', '.mink', '.pak')):
                    unpack_one(os.path.join(root, fn),
                               os.path.join(outroot, os.path.splitext(fn)[0]))
    elif argv:
        outdir = argv[1] if len(argv) > 1 else os.path.splitext(argv[0])[0] + '.unpacked'
        unpack_one(argv[0], outdir)
    else:
        print(__doc__); return 2
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
