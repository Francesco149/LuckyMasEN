#!/usr/bin/env python3
"""
scan_jp.py — find Japanese strings baked into a binary, the way `strings` can't.

The remaining JP after PE-resource translation is drawn at runtime from string
literals compiled into the binaries (e.g. MinkIt's tray menu via AppendMenuA, the
pin-arrow tooltip). Those are NOT in the resource tree, so pe_res.py won't see them.

  - **cp932 (Shift-JIS)** literals (the `*A` ANSI APIs this 2007 MSVC build uses) are
    invisible to `strings -e s`: SJIS lead bytes are >0x7F so a JP run looks like
    garbage interleaved with the few trail bytes that fall in ASCII range.
  - **wide (UTF-16LE)** literals show with `strings -e l`, but that floods you with the
    .rsrc menu/dialog strings (already handled by pe_res) and gives no section context.

This scanner segments the file into maximal cp932 / utf-16-le string runs, keeps only
those containing real kana/kanji, and reports each unique string with its **PE section**
(so you can tell a hardcoded `.rdata`/`.text` literal from an already-handled `.rsrc`
resource), occurrence **count** (binpatch needs a unique match), and first file offset.

Stdlib only. Run from anywhere:
  python tools/scan_jp.py [--enc cp932|utf16|both] [--min N] [--section S] FILE...
"""
import sys, os, struct, argparse, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pe_res import has_jp                                  # actual-kana/CJK predicate


def _printable(s):
    return all(c.isprintable() or c in '\t\n' for c in s)


def cp932_runs(data):
    """Yield (offset, text) for each NUL-terminated field that decodes cleanly as cp932
    and is all-printable. Matching whole NUL-delimited fields (the way a C string literal
    is stored) — not greedy byte runs — is what cuts pointer-table / machine-code noise:
    binary chunks rarely strict-decode as printable cp932 end to end."""
    runs, off = [], 0
    for field in data.split(b'\x00'):
        if field:
            try:
                txt = field.decode('cp932')
            except UnicodeDecodeError:
                txt = None
            if txt is not None and _printable(txt):
                runs.append((off, txt))
        off += len(field) + 1
    return runs


def utf16_runs(data):
    """Yield (offset, text) for maximal printable UTF-16LE runs."""
    i, n = 0, len(data) & ~1
    start, buf = None, []
    runs = []
    while i < n:
        ch = struct.unpack_from('<H', data, i)[0]
        if 0x20 <= ch <= 0xFFFD and ch != 0xFFFF:
            if start is None:
                start = i
            buf.append(ch); i += 2
        else:
            if buf:
                runs.append((start, ''.join(map(chr, buf))))
            start, buf = None, []
            i += 2
    if buf:
        runs.append((start, ''.join(map(chr, buf))))
    return runs


def pe_sections(data):
    """[(name, rawptr, rawsize)] for a PE, else [] — to label each hit's home section."""
    if data[:2] != b'MZ':
        return []
    try:
        e = struct.unpack_from('<I', data, 0x3C)[0]
        if data[e:e + 4] != b'PE\x00\x00':
            return []
        nsec = struct.unpack_from('<H', data, e + 6)[0]
        optsz = struct.unpack_from('<H', data, e + 20)[0]
        tbl = e + 24 + optsz
        out = []
        for k in range(nsec):
            o = tbl + k * 40
            name = data[o:o + 8].rstrip(b'\x00').decode('latin1', 'replace')
            out.append((name, struct.unpack_from('<I', data, o + 20)[0],
                        struct.unpack_from('<I', data, o + 16)[0]))
        return out
    except struct.error:
        return []


def section_of(secs, off):
    for name, ptr, size in secs:
        if ptr <= off < ptr + size:
            return name
    return '(hdr)'


def _jp_count(s):
    return sum(1 for c in s if has_jp(c))


def scan(path, encs, minlen, min_jp, only_section):
    data = open(path, 'rb').read()
    secs = pe_sections(data)
    runs = []
    if 'cp932' in encs:
        runs += [('s', o, t) for o, t in cp932_runs(data)]
    if 'utf16' in encs:
        runs += [('l', o, t) for o, t in utf16_runs(data)]

    # group by (encoding, text): count, sections, first offset
    agg = collections.OrderedDict()
    for enc, off, txt in sorted(runs, key=lambda r: r[1]):
        # min_jp ≥ 2 cuts machine-code false positives (.text bytes rarely form a run
        # of multiple consecutive valid kana/kanji); a real UI string has several.
        if not has_jp(txt) or len(txt) < minlen or _jp_count(txt) < min_jp:
            continue
        sec = section_of(secs, off)
        if only_section:
            if sec not in only_section:
                continue
        elif sec in ('.text', '(hdr)'):       # literals never live in code/headers
            continue
        key = (enc, txt)
        if key not in agg:
            agg[key] = {'n': 0, 'secs': set(), 'first': off}
        agg[key]['n'] += 1
        agg[key]['secs'].add(sec)

    print(f"== {os.path.relpath(path)}  ({len(agg)} unique JP string(s)) ==")
    for (enc, txt), m in sorted(agg.items(), key=lambda kv: kv[1]['first']):
        secs_s = ','.join(sorted(m['secs']))
        print(f"  {enc} @0x{m['first']:06x} [{secs_s:<8}] x{m['n']}  {txt!r}")
    return agg


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--enc', choices=['cp932', 'utf16', 'both'], default='both')
    ap.add_argument('--min', type=int, default=1, help='min decoded length (chars)')
    ap.add_argument('--min-jp', type=int, default=2, dest='min_jp',
                    help='min count of JP chars in a run (2 cuts machine-code noise)')
    ap.add_argument('--section', default=None,
                    help='restrict to these PE sections (comma list, e.g. .rdata,.data). '
                         'Default: all but .text/(hdr), where literals never live.')
    ap.add_argument('files', nargs='+')
    a = ap.parse_args(argv)
    encs = ('cp932', 'utf16') if a.enc == 'both' else (a.enc,)
    only = set(a.section.split(',')) if a.section else None
    for f in a.files:
        scan(f, encs, a.min, a.min_jp, only)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
