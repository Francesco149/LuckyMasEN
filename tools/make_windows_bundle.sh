#!/usr/bin/env bash
# make_windows_bundle.sh — assemble the zero-install Windows self-service bundle.
#
# Runs on Linux (or in `nix develop`) and produces out/LuckyMasEN-builder-win.zip: a
# folder the end user unzips on Windows and runs `build.bat --setup <disc>\setup.exe`.
# It bundles our toolchain + the prebuilt gcalsrv.exe + a cache pre-seeded with the
# Windows builds of the freeware tools (Inno Setup compiler, innounp, innoextract) so
# the build is fully OFFLINE except, on the very first run, fetching Python if the user
# has none. NO SYGNAS bytes and NO Microsoft font are ever in this bundle — the user
# supplies their own disc setup.exe and their own MS PGothic, exactly like the rest of
# the toolchain.
#
# We deliberately do NOT bundle Python (the embeddable + native wheels can only be laid
# down + tested on Windows): build.bat bootstraps a private Python on first run instead.
# The fully-frozen, nothing-on-first-run .exe is produced by the CI workflow on Windows.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; repo="$(cd "$here/.." && pwd)"
out="$repo/out"; stage="$out/LuckyMasEN-builder-win"; dl="$out/_winbundle-dl"
zip_out="$out/LuckyMasEN-builder-win.zip"

# Pinned freeware tools — same versions/sha256 as tools/make_iso.py PINS.
IS_URL="https://files.jrsoftware.org/is/5/innosetup-5.6.1.exe"
IS_SHA="96fd6a5eaab473c61a19affff89618764b940ee3f15837c2944a5595aed5fde6"
UNP_URL="https://downloads.sourceforge.net/project/innounp/innounp/innounp%200.50/innounp050.rar"
UNP_SHA="1d8837540ccc15d98245a1c73fd08f404b2a7bdfe7dc9bed2fdece818ff6df67"
IE_URL="https://github.com/dscharrer/innoextract/releases/download/1.9/innoextract-1.9-windows.zip"
IE_SHA="6989342c9b026a00a72a38f23b62a8e6a22cc5de69805cf47d68ac2fec993065"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing tool: $1 (run inside 'nix develop')" >&2; exit 1; }; }
need curl; need bsdtar; need innoextract; need unzip; need sha256sum
fetch() {  # url sha dest
  mkdir -p "$(dirname "$2")"
  [ -f "$3" ] || curl -fsSL -o "$3" "$1"
  echo "$2  $3" | sha256sum -c - >/dev/null || { echo "checksum FAIL: $3" >&2; exit 1; }
}

echo ">> gcalsrv.exe (our redistributable server)"
[ -f "$repo/tools/gcal-xp/gcalsrv.exe" ] || { echo "build it first: tools/gcal-xp/build.sh" >&2; exit 1; }

echo ">> fetching the Windows freeware tools (pinned + verified)"
mkdir -p "$dl"
fetch "$IS_URL"  "$IS_SHA"  "$dl/innosetup.exe"
fetch "$UNP_URL" "$UNP_SHA" "$dl/innounp.rar"
fetch "$IE_URL"  "$IE_SHA"  "$dl/innoextract-win.zip"

echo ">> staging $stage"
rm -rf "$stage"; mkdir -p "$stage"

# 1) our toolchain (no originals/, no out/, no caches, no retired oracle/runtime junk)
for d in tools patch installer docs; do
  bsdtar -C "$repo" -cf - \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.luabuild' \
    --exclude='gcal-emu' --exclude='gcalsrv.log' --exclude='gcal-xp.ini' \
    "$d" | bsdtar -C "$stage" -xf -
done
cp "$repo/README.md" "$stage/" 2>/dev/null || true

# 2) the cache, pre-seeded with the Windows tool binaries make_iso.py looks for
mkdir -p "$stage/cache/innoextract" "$stage/cache/innounp" "$stage/cache/innosetup"
( cd "$stage/cache/innoextract" && unzip -joq "$dl/innoextract-win.zip" '*innoextract.exe' )
bsdtar -C "$stage/cache/innounp" -xf "$dl/innounp.rar" innounp.exe
ietmp="$(mktemp -d)"; innoextract -e -s -q --output-dir "$ietmp" "$dl/innosetup.exe"
cp -r "$ietmp/app/." "$stage/cache/innosetup/"; rm -rf "$ietmp"   # ISCC.exe + ISPP/ISCmplr/Default.isl
test -f "$stage/cache/innosetup/ISCC.exe"      # the layout make_iso.resolve_iscc expects

# 3) the double-clickable entry point + a short readme
printf '@echo off\r\ncall "%%~dp0installer\\windows\\build.bat" %%*\r\n' > "$stage/build.bat"
cat > "$stage/README.txt" <<'TXT'
LuckyMasterEN - English patched-ISO builder (Windows)
=====================================================

You need TWO of your own files (never redistributed by us):
  1. Your LuckyMas disc's  setup.exe
  2. Your own MS PGothic font (msgothic.ttc) - or let it auto-detect on Windows.

Then, in a Command Prompt in this folder:

    build.bat --setup D:\setup.exe --font auto

(replace D:\setup.exe with the path to your disc's setup.exe). The result is
    out\LuckyMas-EN.iso   (burn or mount on the XP box, run setup.exe)
    out\LuckyMas-EN.zip   (or just unzip and run setup.exe)

First run: if you have no Python, a private copy is fetched automatically. The
Inno Setup compiler / innounp / innoextract are already included in .\cache .
Nothing here contains any SYGNAS or Microsoft file. Full guide: docs\end-user-build.md
TXT

echo ">> zipping $zip_out"
rm -f "$zip_out"
( cd "$out" && bsdtar -a -cf "$zip_out" LuckyMasEN-builder-win )

echo ">> done"
du -sh "$stage" | sed 's/^/   staged: /'
ls -l "$zip_out" | sed 's/^/   zip:    /'
echo "   contents:"; bsdtar -tf "$zip_out" | sed -n '1,40{s/^/     /;p}'   # cap in sed (no | head -> no SIGPIPE under pipefail)
