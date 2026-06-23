#!/usr/bin/env python3
"""get_font.py — obtain MS PGothic (msgothic.ttc) for the LuckyMas installer build.

We ship the TOOLCHAIN, not setup.exe, and we do NOT redistribute the Microsoft font:
the BUILDER supplies their own legally-obtained MS PGothic — exactly like they supply
their own SYGNAS disc. This tool normalizes whatever the builder has into
out/font/msgothic.ttc, which installer/setup.iss bundles into the setup.exe it builds.
That font makes the wizard render the faithful 586x364 AND gives the app's speech-bubble
serifs their real face on an XP without an East-Asian language pack.

Sources (you are licensed to MS PGothic via any of these — see --list-sources):
  --ttf PATH         a msgothic.ttc (or a MS PGothic .ttf) you already have
  --windows PATH     a Windows dir/mount; uses <PATH>/Fonts/msgothic.ttc
  --from-system      auto-detect (e.g. /mnt/c/Windows/Fonts/msgothic.ttc on WSL)
  --langpack PATH    an XP East-Asian lang pack: a dir or .iso with I386\\LANG\\MSGOTHIC.TT_
                     (the LZ-compressed form is decompressed automatically)
  --list-sources     print the legal ways to obtain it, then exit

Output: out/font/msgothic.ttc (validated; out/ is gitignored — never committed).
"""
import argparse, os, shutil, subprocess, sys, tempfile

for _s in (sys.stdout, sys.stderr):           # never crash printing on a cp1252 Windows console
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, 'out', 'font', 'msgothic.ttc')

SOURCES_HELP = r"""How to obtain MS PGothic (msgothic.ttc) — you are licensed to it via any of these:

  1. Your own Windows (any edition with East-Asian fonts present):
       %WINDIR%\Fonts\msgothic.ttc   ->  get_font.py --ttf <that path>
       (on WSL:  get_font.py --from-system   reads /mnt/c/Windows/Fonts/msgothic.ttc)

  2. Turn on East-Asian fonts on any Windows box, then copy msgothic.ttc:
       XP : Control Panel -> Regional and Language Options -> Languages ->
            "Install files for East Asian languages" (pulls from the XP CD's I386).
       7+ : the East-Asian fonts already ship in %WINDIR%\Fonts.

  3. A Windows XP CD or ISO (your own licensed media):
       I386\LANG\MSGOTHIC.TT_ (LZ-compressed)  ->  get_font.py --langpack <iso-or-dir>

  4. Microsoft Office (older builds, East-Asian proofing tools) also installs MS PGothic.

We never ship the font: you build YOUR setup.exe from YOUR disc + YOUR font, exactly like
the rest of this toolchain. The chosen file lands at out/font/msgothic.ttc and is bundled
by installer/setup.iss.  (out/ is gitignored — never committed.)"""


def tool(name, pkg):
    """Command prefix to run `name`, from PATH or via `nix shell nixpkgs#pkg -c`."""
    return [name] if shutil.which(name) else ['nix', 'shell', f'nixpkgs#{pkg}', '-c', name]


def find_font(root):
    """Recursively locate msgothic.ttc or MSGOTHIC.TT_ (case-insensitive) under root."""
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            if f.lower() in ('msgothic.ttc', 'msgothic.tt_'):
                return os.path.join(dp, f)
    return None


def extract_from_iso(iso, dst_dir):
    z = tool('7z', 'p7zip')
    listing = subprocess.run(z + ['l', '-slt', iso], capture_output=True, text=True).stdout
    member = None
    for line in listing.splitlines():
        if line.lower().startswith('path =') and line.lower().rstrip().endswith(('msgothic.tt_', 'msgothic.ttc')):
            member = line.split('=', 1)[1].strip()
            break
    if not member:
        sys.exit(f"{iso}: no MSGOTHIC.TT_/.ttc inside (expected I386\\LANG\\MSGOTHIC.TT_)")
    subprocess.run(z + ['e', f'-o{dst_dir}', iso, member, '-y'], check=True,
                   stdout=subprocess.DEVNULL)
    return os.path.join(dst_dir, os.path.basename(member.replace('\\', '/')))


def decompress(src, dst):
    """XP I386 compressed .TT_ -> .ttc.  XP/2003 ships an MSCF cab; older media use SZDD."""
    with open(src, 'rb') as f:
        magic = f.read(4)
    if magic == b'MSCF':                        # cabinet containing msgothic.ttc
        d = tempfile.mkdtemp()
        subprocess.run(tool('cabextract', 'cabextract') + ['-d', d, src],
                       check=True, stdout=subprocess.DEVNULL)
        inner = find_font(d)
        if not inner:
            sys.exit("cab had no msgothic.ttc inside")
        shutil.move(inner, dst)
        shutil.rmtree(d, ignore_errors=True)
    elif magic[:2] in (b'SZ', b'KW'):           # SZDD / KWAJ
        with open(src, 'rb') as i, open(dst, 'wb') as o:
            subprocess.run(tool('msexpand', 'mscompress'), stdin=i, stdout=o, check=True)
    else:
        sys.exit(f"{src}: unrecognized compression (magic {magic!r}). On Windows: expand \"{src}\" \"{dst}\"")
    if not os.path.exists(dst) or os.path.getsize(dst) == 0:
        sys.exit("decompression produced empty output")


def validate(path):
    with open(path, 'rb') as f:
        magic = f.read(4)
    is_ttc = magic == b'ttcf'
    is_ttf = magic in (b'\x00\x01\x00\x00', b'true', b'OTTO')
    if not (is_ttc or is_ttf):
        sys.exit(f"{path}: not a TrueType font (magic {magic!r}) — is this really MS PGothic?")
    fams = ''
    try:
        fams = subprocess.run(tool('fc-scan', 'fontconfig') + ['--format', '%{family}\n', path],
                              capture_output=True, text=True).stdout
    except Exception:
        pass
    print(f"  {'TTC collection' if is_ttc else 'single TTF'}, {os.path.getsize(path):,} bytes")
    if 'pgothic' in fams.lower() or 'Ｐゴシック' in fams:
        print("  contains MS PGothic [ok]")
    elif not fams.strip():
        print("  (face name not verified here - no fontconfig; assuming MS PGothic)")
    else:
        seen = ', '.join(sorted({x for x in fams.split(chr(10)) if x})[:8])
        print(f"  [!] MS PGothic face not detected (faces: {seen}) - verify this is msgothic.ttc")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=SOURCES_HELP)
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--ttf', metavar='PATH', help='a msgothic.ttc (or MS PGothic .ttf) you have')
    g.add_argument('--windows', metavar='PATH', help='a Windows dir/mount; uses <PATH>/Fonts/msgothic.ttc')
    g.add_argument('--from-system', action='store_true', help='auto-detect from the usual system Fonts dir')
    g.add_argument('--langpack', metavar='PATH', help='XP East-Asian lang pack dir or .iso (I386\\LANG\\MSGOTHIC.TT_)')
    g.add_argument('--list-sources', action='store_true', help='print legal ways to obtain MS PGothic')
    ap.add_argument('--out', default=OUT, help='output path (default out/font/msgothic.ttc)')
    args = ap.parse_args(argv)

    if args.list_sources:
        print(SOURCES_HELP); return 0
    if not any([args.ttf, args.windows, args.from_system, args.langpack]):
        ap.print_help(); return 2

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    tmp = tempfile.mkdtemp()
    try:
        if args.ttf:
            src = args.ttf
        elif args.windows:
            src = next((p for p in (os.path.join(args.windows, c) for c in
                        ('Fonts/msgothic.ttc', 'fonts/msgothic.ttc', 'Fonts/MSGOTHIC.TTC')) if os.path.exists(p)),
                       None) or find_font(args.windows)
        elif args.from_system:
            cands = ['/mnt/c/Windows/Fonts/msgothic.ttc', '/mnt/c/WINDOWS/Fonts/msgothic.ttc',
                     'C:/Windows/Fonts/msgothic.ttc']
            win = os.environ.get('WINDIR') or os.environ.get('SystemRoot')   # native Windows (any drive)
            if win:
                cands.insert(0, os.path.join(win, 'Fonts', 'msgothic.ttc'))
            src = next((p for p in cands if os.path.exists(p)), None)
            if not src:
                sys.exit("no msgothic.ttc in the usual system Fonts dir — use --ttf/--windows/--langpack")
        else:  # --langpack
            lp = args.langpack
            if os.path.isfile(lp) and lp.lower().endswith(('.iso', '.img')):
                src = extract_from_iso(lp, tmp)
            elif os.path.isdir(lp):
                src = find_font(lp)
            else:
                src = lp if os.path.isfile(lp) else None
            if not src:
                sys.exit(f"no MSGOTHIC.TT_/.ttc found under {lp}")

        if not src or not os.path.exists(src):
            sys.exit(f"source not found: {src}")

        if src.lower().endswith('.tt_'):
            print(f"decompressing {src} -> {os.path.basename(args.out)}")
            decompress(src, args.out)
        else:
            print(f"copying {src} -> {args.out}")
            shutil.copyfile(src, args.out)

        validate(args.out)
        print(f"\nOK -> {args.out}\n(installer/setup.iss bundles this; out/ is gitignored — never committed.)")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
