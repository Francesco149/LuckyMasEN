#!/usr/bin/env bash
# make_linux_bundle.sh — assemble the Linux self-service bundle (a tarball).
#
# Produces out/LuckyMasEN-builder-linux.tar.gz: our toolchain + the prebuilt gcalsrv.exe + a cache
# pre-seeded with the Inno Setup compiler + innounp (they run under wine). The user unpacks it and runs
# `./build.sh --setup <disc>/setup.exe --font auto`; on first run it makes a local Python venv with the
# build deps. Host needs python3 + wine + innoextract (build.sh checks). NO SYGNAS bytes, NO Microsoft
# font in the bundle — the user supplies their own disc setup.exe + their own MS PGothic.
#
# (The Windows counterpart is tools/make_windows_bundle.sh; the Nix path is `nix run .#iso`.)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; repo="$(cd "$here/.." && pwd)"
out="$repo/out"; stage="$out/LuckyMasEN-builder-linux"; dl="$out/_linbundle-dl"
tar_out="$out/LuckyMasEN-builder-linux.tar.gz"

# Pinned freeware tools — same versions/sha256 as tools/make_iso.py PINS (ISCC + innounp run via wine).
IS_URL="https://files.jrsoftware.org/is/5/innosetup-5.6.1.exe"
IS_SHA="96fd6a5eaab473c61a19affff89618764b940ee3f15837c2944a5595aed5fde6"
UNP_URL="https://downloads.sourceforge.net/project/innounp/innounp/innounp%200.50/innounp050.rar"
UNP_SHA="1d8837540ccc15d98245a1c73fd08f404b2a7bdfe7dc9bed2fdece818ff6df67"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing tool: $1 (run inside 'nix develop')" >&2; exit 1; }; }
need curl; need bsdtar; need innoextract; need sha256sum; need tar
fetch() { mkdir -p "$(dirname "$2")"; [ -f "$3" ] || curl -fsSL -o "$3" "$1"; echo "$2  $3" | sha256sum -c - >/dev/null || { echo "checksum FAIL: $3" >&2; exit 1; }; }

echo ">> gcalsrv.exe (our redistributable server)"
[ -f "$repo/tools/gcal-xp/gcalsrv.exe" ] || { echo "build it first: tools/gcal-xp/build.sh" >&2; exit 1; }

echo ">> fetching the build tools (pinned + verified)"
mkdir -p "$dl"
fetch "$IS_URL"  "$IS_SHA"  "$dl/innosetup.exe"
fetch "$UNP_URL" "$UNP_SHA" "$dl/innounp.rar"

echo ">> staging $stage"
rm -rf "$stage"; mkdir -p "$stage"
for d in tools patch installer docs; do
  bsdtar -C "$repo" -cf - \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.luabuild' \
    --exclude='gcal-emu' --exclude='gcalsrv.log' --exclude='gcal-xp.ini' \
    "$d" | bsdtar -C "$stage" -xf -
done
cp "$repo/README.md" "$stage/" 2>/dev/null || true

# cache pre-seeded with the tools make_iso.py runs under wine (innoextract comes from the host on Linux)
mkdir -p "$stage/cache/innounp" "$stage/cache/innosetup"
bsdtar -C "$stage/cache/innounp" -xf "$dl/innounp.rar" innounp.exe
ietmp="$(mktemp -d)"; innoextract -e -s -q --output-dir "$ietmp" "$dl/innosetup.exe"
cp -r "$ietmp/app/." "$stage/cache/innosetup/"; rm -rf "$ietmp"
test -f "$stage/cache/innosetup/ISCC.exe"

# entry point + readme
printf '#!/usr/bin/env bash\nexec "$(dirname "$0")/installer/linux/build.sh" "$@"\n' > "$stage/build.sh"
chmod +x "$stage/build.sh" "$stage/installer/linux/build.sh"
cat > "$stage/README.txt" <<'TXT'
LuckyMasterEN - English patched-ISO builder (Linux)
===================================================

You need TWO of your own files (never redistributed by us):
  1. Your LuckyMas disc's  setup.exe
  2. Your own MS PGothic font (msgothic.ttc) - or an XP CD/ISO to extract it from.

Host prerequisites: python3, wine, innoextract (build.sh will tell you if any are missing).
Then, in this folder:

    ./build.sh --setup /path/to/setup.exe --font /path/to/msgothic.ttc
    # (--font auto works if msgothic.ttc is reachable, e.g. on WSL)

Result:
    out/LuckyMas-EN.iso   (burn or mount on the XP box, run setup.exe)
    out/LuckyMas-EN.zip   (or just unzip and run setup.exe)

The Inno Setup compiler + innounp are bundled in ./cache and run under wine. Nothing here
contains any SYGNAS or Microsoft file. Prefer Nix? `nix run github:Francesco149/LuckyMasEN#iso`.
Full guide: docs/end-user-build.md
TXT

echo ">> tarring $tar_out"
rm -f "$tar_out"
( cd "$out" && tar -czf "$tar_out" LuckyMasEN-builder-linux )

echo ">> done"
du -sh "$stage" | sed 's/^/   staged: /'
ls -l "$tar_out" | sed 's/^/   tar:    /'
