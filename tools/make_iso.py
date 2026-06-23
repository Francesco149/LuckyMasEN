#!/usr/bin/env python3
r"""make_iso.py — one command: YOUR disc's setup.exe + YOUR MS PGothic -> an English LuckyMas disc image.

This is the end-user front-door of the LuckyMasterEN toolchain. You own the SYGNAS
「らき☆マス」 disc; this re-wraps an *English* installer from it and packs it back into a
patched ISO (and a plain ZIP) — without anyone ever redistributing a SYGNAS byte (the
copyrighted files stay on your machine; we ship only the patch + this tool).

    python tools/make_iso.py --setup <path-to-your-disc-setup.exe> [--font auto|<path>]

What it does, end to end (each step is a small, separately-runnable tool):
  1. innoextract  YOUR setup.exe                 -> the installed app tree   (the only SYGNAS input)
  2. build_patch  the app tree                   -> out/patched/  (the English delta from patch/)
  3. get_font     YOUR MS PGothic                -> out/font/msgothic.ttc    (Microsoft font; you supply it)
  4. innounp      YOUR setup.exe (embedded\*)    -> out/og-extract/  (the faithful Lucky*Star wizard art)
  5. ISCC         installer/setup.iss            -> out/iss-build/setup.exe  (the English installer)
  6. pycdlib      setup.exe + autorun + icon     -> out/LuckyMas-EN.iso  (+ a .zip of just the installer)

Cross-platform with minimal friction (see docs/end-user-build.md):
  * Windows : ISCC + innounp run NATIVELY (no wine). innoextract is auto-fetched.
  * Linux   : ISCC + innounp run under wine; innoextract comes from your distro / the nix flake.
  * The freeware build tools (Inno Setup compiler, innounp, innoextract) are located on PATH /
    known install dirs, else auto-downloaded to a pinned, SHA-256-verified cache (~/.cache/luckymasen,
    override with $LUCKYMASEN_CACHE). The Windows portable bundle pre-seeds that cache so it is offline.

Only two inputs are ever yours-and-not-ours: your disc's setup.exe, and your own MS PGothic
(any licensed source — see `tools/get_font.py --list-sources`; `--font auto` finds it on Windows/WSL).

Stdlib + pycdlib only. Python 3.8+ (3.11+ uses stdlib tomllib for the patch step; build_patch.py
brings its own toml read).  Run from anywhere; paths are resolved against the repo root.
"""
import argparse, hashlib, os, platform, shutil, ssl, subprocess, sys, urllib.request, zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"
IS_WINDOWS = (os.name == "nt")
CACHE = Path(os.environ.get("LUCKYMASEN_CACHE", Path.home() / ".cache" / "luckymasen"))

# ── Pinned freeware build tools (auto-downloaded only when not already present) ───────────────
# All three are freeware whose licenses permit redistribution; we still fetch-per-user (pinned +
# checksummed) rather than commit binaries.  sha256 = "" means "compute & print on first fetch"
# (a one-time bootstrap convenience — fill the pin from the printed value).  Override any tool with
# its --<tool> flag or by dropping it in the cache / on PATH.
PINS = {
    "innosetup": {  # the Inno Setup compiler (ISCC.exe) — extracted with innoextract, never run as an installer
        "version": "5.6.1",
        "url": "https://files.jrsoftware.org/is/5/innosetup-5.6.1.exe",
        "sha256": "",
        "kind": "innosetup",  # extract via innoextract, then find ISCC.exe
    },
    "innounp": {  # extracts the embedded wizard art from the user's setup.exe
        "version": "0.50",
        "url": "https://downloads.sourceforge.net/project/innounp/innounp/innounp%200.50/innounp050.rar",
        "sha256": "",
        "kind": "rar",  # unpack with bsdtar / 7z, find innounp.exe
        "member": "innounp.exe",
    },
    "innoextract": {  # native Windows build (Linux gets it from the distro / nix flake)
        "version": "1.9",
        "url": "https://github.com/dscharrer/innoextract/releases/download/1.9/innoextract-1.9-windows.zip",
        "sha256": "",
        "kind": "zip",
        "member": "innoextract.exe",
    },
}

# ── tiny logging ─────────────────────────────────────────────────────────────────────────────
_STEP = [0]
def step(msg):
    _STEP[0] += 1
    print(f"\n\033[1;36m[{_STEP[0]}] {msg}\033[0m", flush=True)
def info(msg):  print(f"    {msg}", flush=True)
def ok(msg):    print(f"    \033[32m✓\033[0m {msg}", flush=True)
def die(msg, *, hint=None):
    print(f"\n\033[1;31mError:\033[0m {msg}", file=sys.stderr)
    if hint:
        print(f"\n{hint}", file=sys.stderr)
    sys.exit(1)

# ── platform / exec helpers ──────────────────────────────────────────────────────────────────
def to_win_path(p):
    """A path a Windows EXE will understand: native on Windows; wine's Z:\\ map on *nix."""
    p = Path(p).resolve()
    return str(p) if IS_WINDOWS else "Z:" + str(p).replace("/", "\\")

def run(argv, *, cwd=None, env=None, quiet=False):
    info("$ " + " ".join(str(a) for a in argv))
    r = subprocess.run([str(a) for a in argv], cwd=cwd, env=env,
                       stdout=(subprocess.PIPE if quiet else None),
                       stderr=(subprocess.STDOUT if quiet else None), text=True)
    if r.returncode != 0:
        if quiet and r.stdout:
            sys.stderr.write(r.stdout)
        die(f"command failed (exit {r.returncode}): {argv[0]}")
    return r

def run_pe(exe, args, *, cwd=None):
    """Run a Windows PE: directly on Windows, via wine elsewhere (dedicated reproducible prefix)."""
    if IS_WINDOWS:
        return run([exe, *args], cwd=cwd)
    env = dict(os.environ)
    env.setdefault("WINEPREFIX", str(CACHE / "wineprefix"))
    env.setdefault("WINEDEBUG", "-all")
    Path(env["WINEPREFIX"]).mkdir(parents=True, exist_ok=True)
    wine = shutil.which("wine") or shutil.which("wine64")
    if not wine:
        die("wine not found — needed to run ISCC/innounp on Linux.",
            hint="Install wine (Debian/Ubuntu: `apt install wine`; or use the nix flake: `nix develop`).")
    return run([wine, exe, *args], cwd=cwd, env=env)

# ── download + verify + cache ────────────────────────────────────────────────────────────────
def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def fetch(url, sha256, dest, *, offline=False):
    if dest.exists() and (not sha256 or _sha256(dest) == sha256):
        return dest
    if offline:
        die(f"missing cached download and --offline set: {dest.name}",
            hint=f"Run once online, or place the file at {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    info(f"downloading {url}")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(url, context=ctx, timeout=120) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
    except Exception as e:
        die(f"download failed: {url}\n    {e}",
            hint="Check connectivity, or pass the tool path explicitly (e.g. --iscc / --innounp).")
    got = _sha256(dest)
    if sha256 and got != sha256:
        dest.unlink(missing_ok=True)
        die(f"checksum mismatch for {dest.name}\n    expected {sha256}\n    got      {got}")
    if not sha256:
        info(f"\033[33msha256 (pin me in PINS): {got}\033[0m")
    return dest

def _extract_rar(archive, outdir):
    bsdtar = shutil.which("bsdtar")
    if bsdtar:
        run([bsdtar, "-xf", archive, "-C", outdir], quiet=True); return
    for z in ("7z", "7zz", "7za"):
        if shutil.which(z):
            run([z, "x", "-y", f"-o{outdir}", archive], quiet=True); return
    die("cannot unpack the innounp .rar — no bsdtar/7z found.",
        hint="Install libarchive (bsdtar) or p7zip, or pass --innounp <path-to-innounp.exe>.")

# ── tool resolution: explicit flag -> PATH/known location -> cache -> pinned download ─────────
def resolve_innoextract(override):
    if override: return Path(override)
    if not IS_WINDOWS:
        w = shutil.which("innoextract")
        if w: return Path(w)
    cached = CACHE / "innoextract" / "innoextract.exe"
    if not cached.exists():
        if not IS_WINDOWS:
            die("innoextract not found on PATH.",
                hint="Install it (`apt install innoextract`) or use `nix develop`.")
        p = PINS["innoextract"]
        arc = fetch(p["url"], p["sha256"], CACHE / "dl" / Path(p["url"]).name)
        cached.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(arc) as z:
            for n in z.namelist():
                if n.lower().endswith("innoextract.exe"):
                    cached.write_bytes(z.read(n)); break
    return cached

def resolve_innounp(override):
    for cand in (override,
                 REPO / "out" / "iss-build" / "innounp" / "innounp.exe",
                 TOOLS / "bin" / "innounp.exe",
                 CACHE / "innounp" / "innounp.exe"):
        if cand and Path(cand).exists():
            return Path(cand)
    p = PINS["innounp"]
    arc = fetch(p["url"], p["sha256"], CACHE / "dl" / "innounp050.rar")
    outdir = CACHE / "innounp"; outdir.mkdir(parents=True, exist_ok=True)
    _extract_rar(arc, outdir)
    exe = outdir / "innounp.exe"
    if not exe.exists():
        hit = next((q for q in outdir.rglob("innounp.exe")), None)
        if hit: exe = hit
    if not exe.exists():
        die("innounp.exe not found after unpacking.", hint="Pass --innounp <path>.")
    return exe

def resolve_iscc(override):
    cands = [override]
    if IS_WINDOWS:
        import glob
        for root in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.environ.get("ProgramFiles", r"C:\Program Files")):
            cands += glob.glob(os.path.join(root, "Inno Setup *", "ISCC.exe"))
    else:
        cands += [Path.home() / ".wine-iss" / "drive_c" / "IS5" / "ISCC.exe"]
    cands.append(CACHE / "innosetup" / "ISCC.exe")
    for c in cands:
        if c and Path(c).exists():
            return Path(c)
    # auto-fetch: download the Inno Setup installer and EXTRACT it with innoextract (do not run it)
    p = PINS["innosetup"]
    arc = fetch(p["url"], p["sha256"], CACHE / "dl" / Path(p["url"]).name)
    dest = CACHE / "innosetup"; dest.mkdir(parents=True, exist_ok=True)
    ie = resolve_innoextract(None)
    run([ie, "-e", "-s", "--output-dir", dest, arc], quiet=True)
    iscc = next((q for q in dest.rglob("ISCC.exe")), None)
    if not iscc:
        die("ISCC.exe not found after extracting Inno Setup.",
            hint="Pass --iscc <path-to-ISCC.exe> (install Inno Setup 5.6+/6).")
    # ISCC needs its support files alongside it — flatten if innoextract nested them under app/
    return iscc

# ── pipeline steps ───────────────────────────────────────────────────────────────────────────
def py(*args):
    """Invoke one of our sibling Python tools with the same interpreter."""
    return run([sys.executable, *args])

def stage_extract(setup_exe, work, innoextract):
    step("Extract the app tree from your setup.exe (innoextract)")
    installed = work / "installed"
    if installed.exists():
        shutil.rmtree(installed)
    installed.mkdir(parents=True)
    run([innoextract, "-s", "-q", "--output-dir", installed, setup_exe])
    if not (installed / "app").is_dir():
        die("innoextract produced no app/ tree — is this the LuckyMas disc setup.exe?")
    ok(f"{sum(1 for _ in installed.rglob('*') if _.is_file())} files -> {installed}")
    return work  # build_patch wants the dir CONTAINING installed/

def stage_patch(originals_parent, out_patched):
    step("Apply the English patch (build_patch.py)")
    py(TOOLS / "build_patch.py", "--originals", originals_parent, "--out", out_patched)
    ok(f"patched tree -> {out_patched}")

def stage_font(font_arg, out_font):
    step("Normalise your MS PGothic (get_font.py)")
    if out_font.exists() and font_arg in (None, "auto", "keep") and out_font.stat().st_size > 100_000:
        ok(f"using existing {out_font}")
        return
    if font_arg in (None, "auto"):
        r = subprocess.run([sys.executable, str(TOOLS / "get_font.py"), "--from-system", "--out", str(out_font)])
        if r.returncode != 0:
            die("could not auto-locate MS PGothic.",
                hint="Pass --font <path-to-msgothic.ttc>, or see legal sources:\n"
                     f"    python {TOOLS/'get_font.py'} --list-sources")
    else:
        fp = Path(font_arg)
        flag = "--langpack" if fp.suffix.lower() == ".iso" else "--ttf"
        py(TOOLS / "get_font.py", flag, fp, "--out", out_font)
    ok(f"font -> {out_font}")

def stage_wizard_art(setup_exe, out_embed_parent, innounp):
    step("Extract the faithful Lucky*Star wizard art (innounp)")
    shutil.rmtree(out_embed_parent, ignore_errors=True)   # else innounp's overwrite prompt hangs under wine
    out_embed_parent.mkdir(parents=True, exist_ok=True)
    # innounp -x (extract) -y (assume yes/overwrite) -b (batch/non-interactive) -m (process embedded)
    run_pe(str(innounp), ["-x", "-y", "-b", "-m", f"-d{to_win_path(out_embed_parent)}",
                          to_win_path(setup_exe), r"embedded\*"], cwd=str(out_embed_parent))
    img = out_embed_parent / "embedded" / "WizardImage0.bmp"
    if not img.exists():
        die("wizard art not extracted (embedded\\WizardImage0.bmp missing).",
            hint="Your setup.exe may differ; pass --skip-art to build with no custom wizard image.")
    ok(f"wizard art -> {out_embed_parent / 'embedded'}")

def stage_compile(iscc, out_setup):
    step("Compile the English installer (ISCC / Inno Setup)")
    iss = REPO / "installer" / "setup.iss"
    run_pe(str(iscc), [to_win_path(iss)], cwd=str(REPO / "installer"))
    if not out_setup.exists():
        die(f"ISCC did not produce {out_setup}")
    ok(f"installer -> {out_setup} ({out_setup.stat().st_size/1e6:.1f} MB)")

def _i9(name):
    """An ISO9660 (level-3) 8.3-ish name + version, matching a Joliet long name."""
    stem, _, ext = name.partition(".")
    return (stem[:8].upper() + ("." + ext[:3].upper() if ext else "")) + ";1"

def _write_iso_pycdlib(files, iso_path, vol):
    try:
        import pycdlib
    except ImportError:
        return False
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, joliet=3, vol_ident=vol)
    for src, name in files:
        iso.add_file(str(src), iso_path="/" + _i9(name), joliet_path="/" + name)
    iso.write(str(iso_path)); iso.close()
    return True

def _write_iso_xorriso(files, iso_path, vol, work):
    tool = (shutil.which("xorriso") or shutil.which("genisoimage")
            or shutil.which("mkisofs") or shutil.which("xorrisofs"))
    if not tool:
        return False
    staging = work / "_iso"; shutil.rmtree(staging, ignore_errors=True); staging.mkdir(parents=True)
    for src, name in files:
        shutil.copy2(src, staging / name)
    if Path(tool).name == "xorriso":
        cmd = [tool, "-as", "mkisofs", "-J", "-r", "-V", vol, "-o", str(iso_path), str(staging)]
    else:
        cmd = [tool, "-J", "-r", "-V", vol, "-o", str(iso_path), str(staging)]
    run(cmd, quiet=True)
    return True

def stage_iso(out_setup, patched, iso_path, zip_path, work):
    step("Pack the patched disc image (ISO + ZIP)")
    icon = patched / "app" / "rakimas.ico"
    readme = patched / "app" / "ReadMe.txt"
    autorun = iso_path.parent / "autorun.inf"
    autorun.write_text("[autorun]\r\nicon=rakimas.ico\r\nopen=setup.exe\r\n", encoding="ascii")

    files = [(out_setup, "setup.exe"), (autorun, "autorun.inf")]
    if icon.exists():   files.append((icon, "rakimas.ico"))
    if readme.exists(): files.append((readme, "ReadMe.txt"))

    if not (_write_iso_pycdlib(files, iso_path, "LUCKYMAS_EN")
            or _write_iso_xorriso(files, iso_path, "LUCKYMAS_EN", work)):
        die("no ISO writer available.",
            hint="`pip install pycdlib`, or install xorriso/genisoimage (or use `nix develop`).")
    ok(f"ISO -> {iso_path} ({iso_path.stat().st_size/1e6:.1f} MB)")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(out_setup, "setup.exe")
        if readme.exists(): z.write(readme, "ReadMe.txt")
    ok(f"ZIP -> {zip_path} ({zip_path.stat().st_size/1e6:.1f} MB)")

# ── main ─────────────────────────────────────────────────────────────────────────────────────
def main(argv):
    ap = argparse.ArgumentParser(
        description="Build an English-patched LuckyMas disc image from YOUR own setup.exe + MS PGothic.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--setup", required=True, metavar="PATH",
                    help="your LuckyMas disc's setup.exe (the only SYGNAS input)")
    ap.add_argument("--font", default="auto", metavar="auto|PATH",
                    help="MS PGothic source: 'auto' (find on Windows/WSL), a msgothic.ttc, or an XP .iso")
    ap.add_argument("--out", default=str(REPO / "out"), metavar="DIR", help="output dir (default out/)")
    ap.add_argument("--name", default="LuckyMas-EN", help="basename for the .iso/.zip (default LuckyMas-EN)")
    ap.add_argument("--gcalsrv", metavar="PATH", help="prebuilt gcalsrv.exe (default tools/gcal-xp/gcalsrv.exe)")
    ap.add_argument("--iscc", help="path to ISCC.exe (else discovered / auto-downloaded)")
    ap.add_argument("--innounp", help="path to innounp.exe (else discovered / auto-downloaded)")
    ap.add_argument("--innoextract", help="path to innoextract (else PATH / auto-downloaded)")
    ap.add_argument("--offline", action="store_true", help="never download; only use cached/PATH tools")
    ap.add_argument("--keep-work", action="store_true", help="keep the temp extract dir")
    ap.add_argument("--no-iso", action="store_true", help="stop after the installer (skip ISO/ZIP)")
    args = ap.parse_args(argv)

    setup_exe = Path(args.setup).resolve()
    if not setup_exe.is_file():
        die(f"--setup not found: {setup_exe}")
    out = Path(args.out).resolve()
    work = out / "_build"; work.mkdir(parents=True, exist_ok=True)
    out_patched = out / "patched"
    out_font = out / "font" / "msgothic.ttc"

    print(f"\033[1mLuckyMasterEN — building an English patched ISO\033[0m")
    print(f"  repo:  {REPO}")
    print(f"  input: {setup_exe}")
    print(f"  out:   {out}")
    print(f"  cache: {CACHE}   platform: {platform.system()} ({'native' if IS_WINDOWS else 'wine for ISCC/innounp'})")

    # gcalsrv.exe (our own redistributable server) must be present for the installer to bundle it.
    gcalsrv = Path(args.gcalsrv) if args.gcalsrv else (TOOLS / "gcal-xp" / "gcalsrv.exe")
    if not gcalsrv.exists():
        die(f"gcalsrv.exe not found at {gcalsrv}",
            hint="It ships prebuilt in the release bundles. From source: tools/gcal-xp/build.sh "
                 "(needs the mingw cross-compiler; the nix flake builds it for you).")
    if args.gcalsrv:
        shutil.copy2(gcalsrv, TOOLS / "gcal-xp" / "gcalsrv.exe")

    innoextract = resolve_innoextract(args.innoextract); info(f"innoextract: {innoextract}")
    innounp     = resolve_innounp(args.innounp);         info(f"innounp:     {innounp}")
    iscc        = resolve_iscc(args.iscc);               info(f"ISCC:        {iscc}")

    originals_parent = stage_extract(setup_exe, work, innoextract)
    stage_patch(originals_parent, out_patched)
    stage_font(args.font, out_font)
    stage_wizard_art(setup_exe, out / "og-extract", innounp)
    out_setup = out / "iss-build" / "setup.exe"
    stage_compile(iscc, out_setup)

    if not args.no_iso:
        iso_path = out / f"{args.name}.iso"
        zip_path = out / f"{args.name}.zip"
        stage_iso(out_setup, out_patched, iso_path, zip_path, work)
        print(f"\n\033[1;32mDone.\033[0m  Burn or mount \033[1m{iso_path}\033[0m on your XP box and run setup.exe,")
        print(f"      or just unzip \033[1m{zip_path}\033[0m and run setup.exe.")
        print(f"      sha256(iso) = {_sha256(iso_path)}")
    else:
        print(f"\n\033[1;32mDone.\033[0m  English installer: {out_setup}")

    if not args.keep_work:
        shutil.rmtree(work, ignore_errors=True)

if __name__ == "__main__":
    main(sys.argv[1:])
