#!/usr/bin/env bash
# build.sh — the Linux front-door for the LuckyMasterEN self-service builder (the tarball bundle).
#
#   ./build.sh --setup /path/to/your/disc/setup.exe --font auto
#
# Produces out/LuckyMas-EN.iso (+ .zip) from YOUR LuckyMas disc's setup.exe and YOUR own MS PGothic.
# The Inno Setup compiler + innounp ship in ./cache and run under wine; innoextract is taken from your
# distro. Python deps (pillow, lief, pycdlib) are installed once into a local ./.venv on first run.
set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"   # installer/linux/ -> bundle root
cd "$here"
export LUCKYMASEN_CACHE="$here/cache"

# 1) host prerequisites
miss=()
command -v python3 >/dev/null 2>&1 || miss+=("python3 (3.8+)")
command -v innoextract >/dev/null 2>&1 || miss+=("innoextract  (e.g. apt install innoextract / nix-shell -p innoextract)")
{ command -v wine >/dev/null 2>&1 || command -v wine64 >/dev/null 2>&1; } || miss+=("wine  (runs the bundled ISCC/innounp)")
if [ ${#miss[@]} -gt 0 ]; then
  printf 'Missing prerequisite(s):\n'; printf '  - %s\n' "${miss[@]}"
  printf 'Install them and re-run. (Or, with Nix: `nix run github:Francesco149/LuckyMasEN#iso -- --setup … --font auto`.)\n'
  exit 1
fi

# 2) private Python venv with the build deps (first run only)
PY="$here/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "setting up a local Python environment (one-time)…"
  python3 -m venv "$here/.venv"
  "$PY" -m pip install --quiet --upgrade pip
  "$PY" -m pip install --quiet pillow lief pycdlib
fi

# 3) run the shared engine (resolves ISCC/innounp from ./cache via wine; innoextract from PATH)
exec "$PY" tools/make_iso.py "$@"
