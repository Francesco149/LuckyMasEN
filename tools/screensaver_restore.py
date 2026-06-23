#!/usr/bin/env python3
r"""screensaver_restore.py — restore the four WORKING LuckyMas screensavers into the patched tree.

The disc shipped only the ScreenTime-for-Flash *engine* `.scr` (one binary, four names) WITHOUT its
content package, so the disc screensavers never run on any locale (a SYGNAS packaging defect — see
`docs/screensaver-re.md`).  SYGNAS later released the working versions on their site as an apology:
four standalone InstallShield-MSI installers that bundle the SAME engine `.scr` plus, per screensaver,
a Flash movie + a `saver.dat` descriptor + a couple of support DLLs/assets, and the Flash Player 8
ActiveX (`Flash8.ocx`).  The owner re-hosted the four installers on archive.org (the original site is
gone).

This tool, given those installers (downloaded + SHA-256-pinned, never committed — the hard rule), does
an EXTRACT-AND-MERGE (it does NOT silently run the GUI installers):

  * the engine `.scr` is already shipped by the patch (byte-identical, sha 6b430059…) — we add only the
    per-screensaver working directory `{sys}\<EN-name> dir\` that the engine looks for next to itself
    (working dir = `<scr-basename> dir`, derived from the .scr filename — proven live), and
  * `{sys}\Macromed\Flash\Flash8.ocx`, registered by the installer ([Files] regserver).

How the payload is laid out: every working-dir file is stored VERBATIM and contiguous in the apology
installer, so we carve each by (offset, size) and verify its SHA-256 (the parent installer is itself
SHA-256-pinned, so the offsets are stable — the same idea as the asmpoke ops).  Two locale fixes make the
result pure-ASCII on disk (goal #2 — app-read filenames must be ASCII or they break on non-JP XP):
  * the content movie (a cp932 name like `ちびキャラズ.swf`) is renamed to `saver.swf`, and
  * `saver.dat`'s NUL-terminated swf-name field (offset 312) is rewritten to `saver.swf`
    (the engine opens the movie by that name via the ANSI API — a cp932 name fails on EN-locale XP).
`Flash8.ocx` is LZX-compressed inside the installer's `Data1.cab`, so it needs a cab tool
(cabextract / 7z / Windows `expand`).

Run standalone or via make_iso.py:
    python tools/screensaver_restore.py --out-sys out/patched/sys
    python tools/screensaver_restore.py --out-sys out/patched/sys --installers-dir work/scr/gdrive

Stdlib only (plus a cab tool on PATH for Flash).  Reproducible; verified end-to-end on real XP.
"""
import argparse, hashlib, os, shutil, ssl, struct, subprocess, sys, tempfile, urllib.request, zipfile
from pathlib import Path

# ── source: the four apology installers (owner-uploaded to archive.org, 2026-06-24) ───────────────
# Never committed: downloaded at build, pinned by SHA-256 (zip and inner setup.exe).  Local copies of
# the inner setup.exe may be supplied with --installers-dir to build offline.
ARCHIVE_BASE = "https://archive.org/download/lucky-mas-screensavers"

# Flash Player 8 ActiveX — identical Data1.cab in all four installers (LZX-compressed).
FLASH_OCX_SHA = "31453fd8f743c19e27f8fa04ee88dfebe95a7884cdfbc15ab0eb8994829aad61"
FLASH_OCX_NAME = "Flash8.ocx"            # destination name (matches the real Flash installer)
FLASH_CAB_MEMBER = "flash8.ocx"          # cab member stem (carries a GUID suffix in the cabinet)

# saver.dat: the engine reads the movie filename from a NUL-terminated field here; we rewrite it ASCII.
SAVERDAT_SWF_FIELD = 312                  # offset of the swf-name field in saver.dat
SAVERDAT_SWF_FIELD_END = 380             # the field runs up to here (NUL-padded); names are <= 21 bytes
SWF_NAME = b"saver.swf"                   # ASCII movie name we standardise on (per-dir, no collisions)

# Per screensaver: the archive.org zip + its inner setup.exe (both SHA-256-pinned), the EN .scr name
# whose " dir" working directory we populate, and the VERBATIM (name, offset, size, sha256) carves.
# saver.dat is carved verbatim (its 6 install-time bytes at 388..397 are runtime state — zero is fine,
# proven live) then ASCII-patched; `patched_saver_dat` is the expected post-patch SHA-256 (self-check).
SCREENSAVERS = {
    "chibi": {
        "zip": "scr_chibi.zip",
        "zip_sha256": "fda48017c68a9f70af63cff75a4692675753ebe75adb8d418395eb18ec51b4ab",
        "exe": "chibi_setup.exe",
        "exe_sha256": "9ec7cea2d9823ffcaa88746aaa5ca4a8924553074e839e3b5dee057cdd73b36b",
        "en_name": "LuckyMas - Chibi Characters",
        "patched_saver_dat": "807b1a94e94651917be77181d10e31ada33b2d1d383fc330fa03dd427af7a9bb",
        "files": [  # (out_name, offset, size, src_sha256)
            ("saver.swf",   2311908,  149505, "7a76f1a7d639c61edd8df2ab4a50ee227be24ec165d8401c84d0059567b5f99a"),
            ("saver.dat",   2309832,    1240, "8631bd1580f2b5ecf28633e4b1b1e6abee637b880647318195a9ff7d5db374a7"),
            ("prevmon.scf", 2461457,   51128, "f0c61121fca1ba2426700694ad351c38689c3a6a1c04daf6e055db09c0a3e03e"),
            ("setwnd.scf",  1947216,  157856, "6b94890fb9a51515c3a2c61d9c82edfcd3d6781b876511999cfc97a07c8eabfa"),
            ("expire.scf",  2308336,    1496, "a32d6fcf80d6789f66d327ea6726bb8ced1ab749e2088c1bedeb18f29adb7ce5"),
            ("saver1.dll",  2670485,   34304, "f79c28f4ce13695bf2ec04aa6217238e160ada3a7619392f1b7d390e93363c13"),
            ("saver2.dll",  2704789,   18192, "d88ad399f7dc2d4830e7af1be3bfbf45aaf75e309f0b6afd8a9c4025bf19930e"),
        ],
    },
    "imas3d": {
        "zip": "scr_imas3d.zip",
        "zip_sha256": "b06f1742906d4750fa847c6489360dc470a463f6ae92c8fde4c070abfda99804",
        "exe": "imas3d_setup.exe",
        "exe_sha256": "f9bede370f43396e56963f07afb77220fa6efeef49dbbf8702fc88f903edce17",
        "en_name": "LuckyMas - iM@S 3D",
        "patched_saver_dat": "21ec0caa30a5d725605e883d02897d22c4eb82e2d7e7784a1b625e49916655b4",
        "files": [
            ("saver.swf",   2311908, 13369073, "7eb9666c77087d0d9d1d141f8a5b83122cfe6625a13d5501d19e1d1b8e6ec42a"),
            ("saver.dat",   2309832,     1240, "446f95006a85d61d8c205068c91582fd1495299685748956331007149a4ee68a"),
            ("prevmon.scf", 15681025,   51128, "87751dc913c4b80d2b5e46951752881700b3bc0d7e903f013a92d05c8e79dd1e"),
            ("setwnd.scf",  1947216,   157856, "5692c1e81113dc1f6840cf51ebff86a88b848e260af8af86fc832a2596758a9e"),
            ("expire.scf",  2308336,     1496, "a32d6fcf80d6789f66d327ea6726bb8ced1ab749e2088c1bedeb18f29adb7ce5"),
            ("saver1.dll",  15890053,   34304, "f79c28f4ce13695bf2ec04aa6217238e160ada3a7619392f1b7d390e93363c13"),
            ("saver2.dll",  15924357,   18192, "d88ad399f7dc2d4830e7af1be3bfbf45aaf75e309f0b6afd8a9c4025bf19930e"),
        ],
    },
    "imas_comic": {
        "zip": "scr_imas_comic.zip",
        "zip_sha256": "4d1f55068a704f59968316848500cf96c769d60f6efcb6d8c42496c99d725df5",
        "exe": "imas_comic_setup.exe",
        "exe_sha256": "e8f15e5445c588fe3be41a340e7113889c34736d5ff2bc4656972015ce580bbb",
        "en_name": "LuckyMas - iM@S Comic",
        "patched_saver_dat": "1ee819322ce199ee40dc3e202ca2da0c842c8ee86ef32c996226647eb947754c",
        "files": [
            ("saver.swf",   2311908,  4137114, "3ef41389e985b54aaadd0b57a003e6ef961189ebd5f56c731aa78ebbc1f938b5"),
            ("saver.dat",   2309832,     1240, "455bfafafe8dc4f56accafb165a090f4126054eca1fc52b314acb613c77eaf78"),
            ("prevmon.scf", 6449066,    51128, "e8840e7123fef389505f69a0db099b7ebf29ac61f82d3b562656aae958f73cb9"),
            ("setwnd.scf",  1947216,   157856, "b1e64212639c3af122df489c496216012d57ee5aaa8873eba4e1cd48a1836f1c"),
            ("expire.scf",  2308336,     1496, "a32d6fcf80d6789f66d327ea6726bb8ced1ab749e2088c1bedeb18f29adb7ce5"),
            ("saver1.dll",  6658094,    34304, "f79c28f4ce13695bf2ec04aa6217238e160ada3a7619392f1b7d390e93363c13"),
            ("saver2.dll",  6692398,    18192, "d88ad399f7dc2d4830e7af1be3bfbf45aaf75e309f0b6afd8a9c4025bf19930e"),
        ],
    },
    "lucky_comic": {
        "zip": "scr_lucky_comic.zip",
        "zip_sha256": "ce6c23afd3461b97b4d6a884e0dad0bb6a996cdfb298617e96ac172858e8182c",
        "exe": "luckystar_comic_setup.exe",
        "exe_sha256": "b2b7f781ba7a03edad259a87c035e8e7ea8226fa99ae55ec338f239416570870",
        "en_name": "LuckyMas - Lucky Star Comic",
        "patched_saver_dat": "7300a29a8a9362320219de0db9c386fe5ec14931301765b8fe133949730465fd",
        "files": [
            ("saver.swf",   2207932,  3757364, "dc47bc11909c1c9aca07dfd739e21cf2b894f802e761cce7f77fe1fda0e5c902"),
            ("saver.dat",   2205856,     1240, "6e8ce6095cf834763a09fd743586bbb80a7650ec8583119f4ffe40c443b95bc0"),
            ("prevmon.scf", 5965340,    18104, "f49ac2c86c7441b21d34b728cda922c1a0918973c93f9f2d050a63b2036849f4"),
            ("setwnd.scf",  1947216,    53880, "b16e5992025fd74d9813fd07a730b1f6a1aefa55a00623562d3c5506fe4564f8"),
            ("expire.scf",  2204360,     1496, "a32d6fcf80d6789f66d327ea6726bb8ced1ab749e2088c1bedeb18f29adb7ce5"),
            ("saver1.dll",  6037368,    34304, "f79c28f4ce13695bf2ec04aa6217238e160ada3a7619392f1b7d390e93363c13"),
            ("saver2.dll",  6071672,    18192, "d88ad399f7dc2d4830e7af1be3bfbf45aaf75e309f0b6afd8a9c4025bf19930e"),
        ],
    },
}

# ── logging (ASCII + encoding-safe; matches make_iso.py) ──────────────────────────────────────────
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
_COLOR = sys.stdout.isatty() and os.name != "nt"
def _c(code, s): return f"\033[{code}m{s}\033[0m" if _COLOR else s
def info(msg): print(f"    {msg}", flush=True)
def ok(msg):   print("    " + _c("32", "+") + f" {msg}", flush=True)
def warn(msg): print("    " + _c("33", "!") + f" {msg}", flush=True)
class RestoreError(Exception): pass

# ── helpers ──────────────────────────────────────────────────────────────────────────────────────
def _sha256_bytes(b): return hashlib.sha256(b).hexdigest()

def _sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def _fetch(url, sha256, dest, *, offline=False):
    """Download (or reuse a verified cached) file to dest, checking SHA-256."""
    if dest.exists() and _sha256_file(dest) == sha256:
        return dest
    if offline:
        raise RestoreError(f"missing cached download and --offline set: {dest.name}\n"
                           f"      run once online, or place the file at {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    info(f"downloading {url}")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(url, context=ctx, timeout=180) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
    except Exception as e:
        raise RestoreError(f"download failed: {url}\n      {e}")
    got = _sha256_file(dest)
    if got != sha256:
        dest.unlink(missing_ok=True)
        raise RestoreError(f"checksum mismatch for {dest.name}\n"
                           f"      expected {sha256}\n      got      {got}")
    return dest

def _unzip_single_exe(zip_path, exe_name, exe_sha256, dest):
    """Extract the single inner setup.exe from an archive.org zip, verifying its SHA-256."""
    with zipfile.ZipFile(zip_path) as z:
        member = next((n for n in z.namelist() if n.rsplit("/", 1)[-1].lower() == exe_name.lower()), None)
        if member is None:
            raise RestoreError(f"{zip_path.name} does not contain {exe_name}")
        data = z.read(member)
    got = _sha256_bytes(data)
    if got != exe_sha256:
        raise RestoreError(f"checksum mismatch for {exe_name}\n"
                           f"      expected {exe_sha256}\n      got      {got}")
    dest.write_bytes(data)
    return dest

def _carve(setup, off, size, want_sha, what):
    chunk = setup[off:off + size]
    if len(chunk) != size:
        raise RestoreError(f"{what}: cannot carve {size} bytes at {off} (file too short)")
    got = _sha256_bytes(chunk)
    if got != want_sha:
        raise RestoreError(f"{what}: SHA-256 mismatch\n      expected {want_sha}\n      got      {got}")
    return chunk

def _patch_saver_dat(src):
    """Rewrite saver.dat's swf-name field (offset 312) to the ASCII SWF_NAME, NUL-padded."""
    b = bytearray(src)
    for i in range(SAVERDAT_SWF_FIELD, SAVERDAT_SWF_FIELD_END):
        b[i] = 0
    b[SAVERDAT_SWF_FIELD:SAVERDAT_SWF_FIELD + len(SWF_NAME)] = SWF_NAME
    return bytes(b)

def _find_cab_tool():
    """Return (kind, exe) for a usable cab extractor, or None."""
    for exe in ("cabextract",):
        if shutil.which(exe): return ("cabextract", exe)
    for exe in ("7z", "7zz", "7za"):
        if shutil.which(exe): return ("7z", exe)
    if os.name == "nt":
        expand = shutil.which("expand") or r"C:\Windows\System32\expand.exe"
        if Path(expand).exists(): return ("expand", expand)
    return None

def _cfb_extract_cab(setup):
    """Reassemble the embedded Data1.cab stream from the InstallShield MSI (an OLE compound document).

    The cab is an MSI stream fragmented across the compound document's FAT sectors, so a flat byte
    carve is wrong — we walk the CFB FAT and concatenate the chain.  The cab is located by signature
    (the big stream whose first sector starts with 'MSCF'), avoiding MSI's name mangling.
    """
    OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    base = setup.find(OLE)
    if base < 0:
        raise RestoreError("embedded MSI (OLE compound document) not found in installer")
    cfb = setup[base:]
    ssz = 1 << struct.unpack_from("<H", cfb, 30)[0]   # sector size (typically 4096)
    minicut = struct.unpack_from("<I", cfb, 56)[0]    # mini-stream cutoff (typically 4096)
    dirstart = struct.unpack_from("<I", cfb, 48)[0]
    difstart = struct.unpack_from("<I", cfb, 68)[0]
    ndif = struct.unpack_from("<I", cfb, 72)[0]
    def sect(i):
        o = 512 + i * ssz
        return cfb[o:o + ssz]
    difat = list(struct.unpack_from("<109I", cfb, 76))
    s = difstart
    for _ in range(ndif):                              # follow any extra DIFAT sectors
        v = struct.unpack_from(f"<{ssz // 4}I", sect(s)); difat += list(v[:-1]); s = v[-1]
    difat = [x for x in difat if x != 0xFFFFFFFF]
    fat = []
    for fs in difat:
        fat += list(struct.unpack_from(f"<{ssz // 4}I", sect(fs)))
    def chain(c):
        out = []
        while c < 0xFFFFFFFE and c < len(fat):
            out.append(c); c = fat[c]
        return out
    dirdata = b"".join(sect(i) for i in chain(dirstart))
    for i in range(0, len(dirdata), 128):
        e = dirdata[i:i + 128]
        if len(e) < 128:
            break
        if e[66] != 2:                                 # objType 2 = stream
            continue
        size = struct.unpack_from("<Q", e, 120)[0]
        start = struct.unpack_from("<I", e, 116)[0]
        if size <= minicut:                            # the cab is a big stream (in the main FAT)
            continue
        if sect(start)[:4] == b"MSCF":
            return b"".join(sect(x) for x in chain(start))[:size]
    raise RestoreError("Data1.cab (MSCF stream) not found in the embedded MSI")

def _extract_flash(setup, out_path):
    """Extract Data1.cab from the installer's MSI and unpack Flash8.ocx (LZX) via a cab tool; verify SHA."""
    cab = _cfb_extract_cab(setup)
    tool = _find_cab_tool()
    if tool is None:
        raise RestoreError("no cab extractor found (need cabextract, 7z, or Windows expand) for Flash8.ocx")
    kind, exe = tool
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        cabp = td / "Data1.cab"; cabp.write_bytes(cab)
        outdir = td / "out"; outdir.mkdir()
        if kind == "cabextract":
            cmd = [exe, "-q", "-d", str(outdir), "-F", FLASH_CAB_MEMBER + "*", str(cabp)]
        elif kind == "7z":
            cmd = [exe, "e", "-y", f"-o{outdir}", str(cabp), FLASH_CAB_MEMBER + "*"]
        else:  # expand (Windows)
            cmd = [exe, str(cabp), f"-F:{FLASH_CAB_MEMBER}*", str(outdir)]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if r.returncode != 0:
            raise RestoreError(f"cab extraction failed ({exe}):\n{r.stdout}")
        hit = next((p for p in outdir.rglob("*")
                    if p.is_file() and p.name.lower().startswith(FLASH_CAB_MEMBER)), None)
        if hit is None:
            raise RestoreError(f"{FLASH_CAB_MEMBER} not found in Data1.cab after extraction")
        data = hit.read_bytes()
    got = _sha256_bytes(data)
    if got != FLASH_OCX_SHA:
        raise RestoreError(f"{FLASH_OCX_NAME}: SHA-256 mismatch\n"
                           f"      expected {FLASH_OCX_SHA}\n      got      {got}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    return out_path

# ── main API ─────────────────────────────────────────────────────────────────────────────────────
def restore(out_sys, *, cache, offline=False, installers_dir=None, with_flash=True):
    """Populate out_sys with the four screensaver working dirs + Flash8.ocx.

    out_sys        : the patched tree's sys/ dir (e.g. out/patched/sys) — must already hold the .scr.
    cache          : a dir for downloaded zips / extracted installers (default shares make_iso's cache).
    installers_dir : if given, use local inner setup.exe files from here instead of downloading.
    """
    out_sys = Path(out_sys); out_sys.mkdir(parents=True, exist_ok=True)
    cache = Path(cache); dldir = cache / "dl"; exedir = cache / "screensavers"
    exedir.mkdir(parents=True, exist_ok=True)

    made = []
    flash_done = False
    for key, ss in SCREENSAVERS.items():
        # locate the installer (local override, else cached/downloaded zip -> inner exe)
        if installers_dir:
            exe_path = Path(installers_dir) / ss["exe"]
            if not exe_path.exists():
                raise RestoreError(f"--installers-dir given but {exe_path} not found")
            if _sha256_file(exe_path) != ss["exe_sha256"]:
                raise RestoreError(f"{exe_path} SHA-256 does not match the pinned {ss['exe']}")
        else:
            zip_path = _fetch(f"{ARCHIVE_BASE}/{ss['zip']}", ss["zip_sha256"], dldir / ss["zip"], offline=offline)
            exe_path = exedir / ss["exe"]
            if not (exe_path.exists() and _sha256_file(exe_path) == ss["exe_sha256"]):
                _unzip_single_exe(zip_path, ss["exe"], ss["exe_sha256"], exe_path)
        setup = exe_path.read_bytes()

        # write the working dir "<EN-name> dir" next to the (already-shipped) .scr
        wdir = out_sys / f"{ss['en_name']} dir"
        if wdir.exists():
            shutil.rmtree(wdir)
        wdir.mkdir(parents=True)
        for name, off, size, want in ss["files"]:
            data = _carve(setup, off, size, want, f"{key}/{name}")
            if name == "saver.dat":
                data = _patch_saver_dat(data)
                got = _sha256_bytes(data)
                if got != ss["patched_saver_dat"]:
                    raise RestoreError(f"{key}/saver.dat post-patch SHA-256 mismatch\n"
                                       f"      expected {ss['patched_saver_dat']}\n      got      {got}")
            (wdir / name).write_bytes(data)
        ok(f"{ss['en_name']} dir/  ({len(ss['files'])} files)")
        made.append(wdir)

        # Flash8.ocx is the same in every installer — extract it once
        if with_flash and not flash_done:
            flash = out_sys / "Macromed" / "Flash" / FLASH_OCX_NAME
            _extract_flash(setup, flash)
            ok(f"Macromed/Flash/{FLASH_OCX_NAME}  (Flash Player 8 ActiveX)")
            made.append(flash); flash_done = True

    if with_flash and not flash_done:
        warn("Flash8.ocx was not extracted (no screensavers processed?)")
    return made

# ── CLI ──────────────────────────────────────────────────────────────────────────────────────────
def main(argv):
    ap = argparse.ArgumentParser(
        description="Restore the four working LuckyMas screensavers into the patched sys/ tree.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--out-sys", required=True, metavar="DIR",
                    help="the patched tree's sys/ dir (e.g. out/patched/sys) — must already hold the .scr")
    ap.add_argument("--cache", default=str(Path(os.environ.get(
                    "LUCKYMASEN_CACHE", Path.home() / ".cache" / "luckymasen")), ),
                    metavar="DIR", help="download/extract cache (default ~/.cache/luckymasen)")
    ap.add_argument("--installers-dir", metavar="DIR",
                    help="use local inner setup.exe files from here instead of downloading the zips")
    ap.add_argument("--offline", action="store_true", help="never download; only use cached files")
    ap.add_argument("--no-flash", action="store_true", help="do not extract/register Flash8.ocx")
    args = ap.parse_args(argv)
    try:
        made = restore(args.out_sys, cache=args.cache, offline=args.offline,
                       installers_dir=args.installers_dir, with_flash=not args.no_flash)
    except RestoreError as e:
        print("\n" + _c("1;31", "Error:") + f" {e}", file=sys.stderr)
        return 1
    print(_c("1;32", f"Done. restored {len(made)} item(s) into {args.out_sys}"))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
