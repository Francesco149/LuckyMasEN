#!/usr/bin/env python3
"""
sygnas_unpack.py — unpacker for the SYGNAS 「らき☆マス」(2007) container formats.

Handles the three chunk formats reverse-engineered in docs/mink-format.md:
  MINK     (*.mink)  — mascot copy/download animations  (chunks: info, a0, m0)
  ACZ      (*.Xvi)   — launcher character assets          (CharaMainNN PNGs + an Ini)
  PACKDATA (*.pak)   — calculator assets                  (PNGs + Squirrel *.nut)

Compression: the launcher's ACZ text blob (the `Ini` chunk = the character's
speech/dialogue) uses canonical **Okumura LZSS** (N=4096, F=18, THRESHOLD=2, ring
pre-filled with 0x20, flag bit set = literal). The calc PACKDATA `.nut` (Squirrel
source) blobs use a *different* LZSS (see `pak_decompress`) — also cracked, so they
are emitted decoded. The `.mink` `info` chunk (per-character Title=/Author=/… metadata)
uses a **third** LZSS — MinkIt's own MSB-first bit codec (see `mink_info_decompress`),
also cracked, so it is emitted as decoded cp932 text. Only the `.mink` a0/m0 sprite
streams use a still-unknown codec and are emitted raw, with a `.raw` suffix.

Stdlib only — runs anywhere (no flake needed). Reversible; reads originals, never writes them.

Usage:
  sygnas_unpack.py <file.Xvi|.mink|.pak> [outdir]      # one container
  sygnas_unpack.py --dir <indir> <outdir>              # every container under indir
"""
import os, sys, struct

def u32(b, o): return struct.unpack_from('<I', b, o)[0]

def mink_chunks(b):
    """Return {chunk-name: (offset, size)} for a MINK container directory (info/a0/m0)."""
    assert b[:4] == b'MINK', "not a MINK container"
    d = {}
    for k in range(u32(b, 8)):
        o = 16 + k * 16
        name = b[o:o+8].split(b'\x00')[0].decode('latin1')
        d[name] = (u32(b, o+8), u32(b, o+12))
    return d

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

# ---- PACKDATA (.pak .nut) LZSS — the calculator Squirrel-script codec -----------
def pak_decompress(data, usize, WINDOW=4096):
    """The calc `data.pak` `.nut` codec (distinct from the ACZ/Okumura text codec above):
    a control byte's 8 bits are read **MSB-first**, bit **set = literal** (one byte), bit
    **clear = match** (a 2-byte token b0,b1) with
        length   = (b0 & 0x0f) + 2                      # 2..17
        distance = ((b0 >> 4) | (b1 << 4)) + 1          # 1..4096 (12-bit window)
    and the copy is overlap-capable (RLE: length may exceed distance). Byte-exact on all
    four .nut (`usize` matches; output is clean Squirrel source)."""
    out = bytearray(); i = 0; flags = 0; nbits = 0; L = len(data)
    while len(out) < usize and i < L:
        if nbits == 0:
            flags = data[i]; i += 1; nbits = 8
        bit = (flags >> 7) & 1; flags = (flags << 1) & 0xff; nbits -= 1
        if bit:
            out.append(data[i]); i += 1
        else:
            b0, b1 = data[i], data[i + 1]; i += 2
            length = (b0 & 0x0f) + 2
            src = len(out) - (((b0 >> 4) | (b1 << 4)) + 1)
            for k in range(length):
                out.append(out[src + k])
    return bytes(out)

# ---- MINK (.mink) `info`-chunk LZSS — MinkIt's own per-character metadata codec --
def _mink_decode(chunk):
    """Faithful port of MinkIt.dll FUN_100023e0 (decoder) + FUN_10002350 (bit reader).
    The `info` chunk is `[u32 decompressed_size][bitstream]`. Bits are read **MSB-first**
    across byte boundaries; per token a control bit selects: 0 = literal (next 8 bits = one
    byte), 1 = back-reference (8-bit distance back, then 4-bit length; copied byte-by-byte so
    overlap/RLE is allowed). The engine stops on **source EOF** — its bit reader signals EOF
    the moment it loads the final source byte, so that last byte is an unread terminator.
    Returns the raw decoded stream (may include encoder NUL-padding past decompressed_size)."""
    src = chunk; L = len(src)
    st = {'pos': 4, 'buf': 0, 'cnt': 0xff}            # pos starts after the u32 size header
    def get_bit():
        if st['cnt'] == 0xff:                         # 0xff = "need to load the next byte"
            st['buf'] = src[st['pos']]; st['pos'] += 1
            if st['pos'] >= L:                        # EOF: the byte just loaded is discarded
                return None
            st['cnt'] = 7
        c = st['cnt']; st['cnt'] = (c - 1) & 0xff     # 7..0 then wraps to 0xff -> reload
        return (st['buf'] >> c) & 1
    def get_bits(n):
        v = 0
        for _ in range(n):
            b = get_bit()
            if b is None:
                return None
            v = (v << 1) | b
        return v
    out = bytearray()
    while True:
        ctrl = get_bit()
        if ctrl is None:
            break
        if ctrl == 0:                                 # literal: 8 data bits
            v = get_bits(8)
            if v is None:
                break
            out.append(v)
        else:                                         # back-reference: 8-bit dist, 4-bit len
            dist = get_bits(8); length = get_bits(4)
            if dist is None or length is None:
                break
            start = len(out) - dist
            for k in range(length):
                out.append(out[start + k])
    return bytes(out)

def mink_info_decompress(chunk):
    """Decode a MINK `info` chunk to its logical text (Title=/Author=/RefURL=/Pattern=/
    Interval=, cp932), sliced to the stored decompressed_size. See `_mink_decode`."""
    out_size = u32(chunk, 0)
    return _mink_decode(chunk)[:out_size]


# ---- container parsers: each yields (name, data, kind) --------------------------
# kind: 'text' = decoded UTF-able config | 'asset' = ready file (PNG/…) | 'raw' = unknown codec
def parse_mink(b):
    assert b[:4] == b'MINK'
    for k in range(u32(b, 8)):
        o = 16 + k * 16
        name = b[o:o+8].split(b'\x00')[0].decode('latin1')
        off, size = u32(b, o+8), u32(b, o+12)
        chunk = b[off:off+size]
        if name == 'info':                             # per-character metadata (LZSS, cracked)
            yield (name, mink_info_decompress(chunk), 'text')
        else:
            yield (name, chunk, 'raw')                 # a0/m0 sprite codec still unknown -> raw

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
        if stored != usize:                            # compressed (the 4 Squirrel .nut)
            yield (name, pak_decompress(raw, usize), 'asset')
        else:                                          # PNG stored 1:1
            yield (name, raw, 'asset')

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
