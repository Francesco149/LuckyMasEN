#!/usr/bin/env python3
"""
sygnas_repack.py — re-encode an edited ACZ (.Xvi) `Ini` chunk back into the container.

Companion to sygnas_unpack.py. Provides an Okumura-LZSS *encoder* that is byte-for-byte
decode-compatible with the game's decompressor (same params: N=4096, F=18, THRESHOLD=2,
ring init 0x20, flag bit set = literal), and an ACZ rewriter that swaps the `Ini` text for a
translated one and fixes the directory (offset / stored / usize). The per-chunk `tag` is a
constant type id (0x8b878b01 for every Ini, not a checksum), so it is preserved verbatim.

The encoder only emits non-overlapping back-references into already-written history, so the
output is always safely decodable; it is not size-optimal, but every Ini round-trips exactly.

Usage:
  sygnas_repack.py <orig.Xvi> <new_ini.txt> <out.Xvi>   # rebuild one .Xvi with a new Ini (cp932 text in)
  sygnas_repack.py --selftest <dir-of-.Xvi>             # prove encode∘decode == identity on all originals
"""
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sygnas_unpack import lzss_decompress, u32

def lzss_compress(data, N=4096, F=18, THRESHOLD=2, init=0x20):
    win = bytearray([init]) * N
    R0 = N - F                       # decoder's initial ring write position (4078)
    out = bytearray(); i = 0; a = 0  # i: input pos, a: output index (== ring advance)
    flags = 0; nflag = 0; group = bytearray()
    def flush():
        nonlocal flags, nflag, group
        out.append(flags); out.extend(group); flags = 0; nflag = 0; group = bytearray()
    n = len(data)
    while i < n:
        wb = bytes(win)              # decoder's ring state right now
        best_len, best_pos = 0, 0
        maxlen = min(F, n - i)
        L = maxlen
        while L >= THRESHOLD + 1:     # longest non-overlapping match in current ring
            idx = wb.find(data[i:i + L])
            if idx != -1:
                best_len, best_pos = L, idx; break
            L -= 1
        if best_len >= THRESHOLD + 1:
            group.append(best_pos & 0xff)
            group.append(((best_pos >> 4) & 0xf0) | ((best_len - (THRESHOLD + 1)) & 0x0f))
            for k in range(best_len):
                win[(R0 + a) % N] = data[i + k]; a += 1
            i += best_len
        else:                        # literal
            flags |= (1 << nflag)
            group.append(data[i]); win[(R0 + a) % N] = data[i]; a += 1; i += 1
        nflag += 1
        if nflag == 8: flush()
    if nflag: flush()
    return bytes(out)

def acz_entries(b):
    out = []
    for k in range(u32(b, 8)):
        o = 16 + k * 32
        name = b[o:o+16].split(b'\x00')[0].decode('latin1')
        out.append((name, u32(b, o+16), u32(b, o+20), u32(b, o+24), u32(b, o+28)))
    return out

def repack_acz(orig, new_ini_bytes):
    """Rebuild an ACZ container, replacing the Ini chunk's text with new_ini_bytes (raw bytes)."""
    ents = acz_entries(orig)
    count = u32(orig, 8)
    chunks = []                      # (name, blob, usize, tag) in original order
    for name, off, stored, usize, tag in ents:
        if name == 'Ini':
            comp = lzss_compress(new_ini_bytes)
            assert lzss_decompress(comp, expected=len(new_ini_bytes)) == new_ini_bytes, \
                "encoder/decoder mismatch — refusing to write a corrupt chunk"
            chunks.append((name, comp, len(new_ini_bytes), tag))
        else:
            chunks.append((name, orig[off:off+stored], usize, tag))
    data_start = 16 + count * 32
    head = bytearray(orig[:16])
    dirbuf, databuf, cur = bytearray(), bytearray(), data_start
    for name, blob, usize, tag in chunks:
        namef = name.encode('latin1')[:16].ljust(16, b'\x00')
        dirbuf += namef + struct.pack('<IIII', cur, len(blob), usize, tag)
        databuf += blob; cur += len(blob)
    return bytes(head + dirbuf + databuf)

def get_ini(b):
    for name, off, stored, usize, tag in acz_entries(b):
        if name == 'Ini':
            return lzss_decompress(b[off:off+stored], expected=usize)
    return None

def selftest(d):
    import glob
    ok = bad = 0
    for f in sorted(glob.glob(os.path.join(d, '*.Xvi'))):
        b = open(f, 'rb').read()
        ini = get_ini(b)
        # 1) encoder round-trips the text
        rt = lzss_decompress(lzss_compress(ini), expected=len(ini))
        # 2) full container rebuild re-extracts the identical Ini
        rebuilt = get_ini(repack_acz(b, ini))
        good = (rt == ini) and (rebuilt == ini)
        orig_stored = [s for n, o, s, u, t in acz_entries(b) if n == 'Ini'][0]
        enc = len(lzss_compress(ini))
        print(f"  {'ok ' if good else 'FAIL'} {os.path.basename(f):<16} ini={len(ini):4d}b  "
              f"ours={enc:4d}b  orig={orig_stored:4d}b")
        ok += good; bad += (not good)
    print(f"\n{ok} ok, {bad} fail")
    return bad == 0

def main(argv):
    if len(argv) == 2 and argv[0] == '--selftest':
        return 0 if selftest(argv[1]) else 1
    if len(argv) == 3:
        orig = open(argv[0], 'rb').read()
        new_ini = open(argv[1], 'rb').read()
        out = repack_acz(orig, new_ini)
        open(argv[2], 'wb').write(out)
        print(f"wrote {argv[2]}  ({len(out)} bytes; Ini {len(new_ini)}b text)")
        return 0
    print(__doc__); return 2

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
