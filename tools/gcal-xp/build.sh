#!/usr/bin/env bash
# build.sh — cross-compile gcalsrv.exe for Windows XP (i686, subsystem 5.1).
#
# Schannel/CryptoAPI server + Winsock; links ws2_32/secur32/crypt32. The
# subsystem-version override + _WIN32_WINNT=0x0501 make the PE load on XP SP3.
# GUI subsystem (-mwindows) = no console window (autostarted background server;
# also avoids wedging the xphttpd agent's pipe — launch it via `start`).
#
# nixpkgs' mingw libgcc is built --enable-threads=mcf, so the driver adds
# -lmcfgthread. We add the mcfgthreads lib dir to the search path and -static so
# the EXE imports ONLY XP system DLLs (kernel32/ws2_32/secur32/crypt32/msvcrt).
# Verified: no post-XP API is pulled in (the mcf code is dead-stripped; we use
# native CreateThread, not the CRT thread wrapper). -no-pie = fixed-base, XP-safe.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; cd "$here"
CC=i686-w64-mingw32-gcc

# Bring the cross toolchain on PATH from nix if needed (works on wslop + code).
if ! command -v "$CC" >/dev/null 2>&1; then
  exec nix shell nixpkgs#pkgsCross.mingw32.buildPackages.gcc --command bash "$0" "$@"
fi

[ -f cert_pfx.h ] || ./embed-pfx.sh

MCF=$(nix build nixpkgs#pkgsCross.mingw32.windows.mcfgthreads --no-link --print-out-paths | tail -1)

"$CC" gcalsrv.c -o gcalsrv.exe \
  -O2 -s -mwindows -no-pie -static -static-libgcc \
  -D_WIN32_WINNT=0x0501 \
  -Wall -Wextra -Wno-unused-parameter \
  -Wl,--major-subsystem-version=5,--minor-subsystem-version=1 \
  -L"$MCF/lib" -lws2_32 -lsecur32 -lcrypt32

echo "--- built $here/gcalsrv.exe ---"
ls -l gcalsrv.exe

# Sanity: the only imported DLLs must be XP system DLLs (no api-ms-win-*, no mcfgthread).
bad=$(i686-w64-mingw32-objdump -p gcalsrv.exe \
      | grep -i 'DLL Name' \
      | grep -ivE 'KERNEL32|WS2_32|Secur32|CRYPT32|msvcrt|ADVAPI32|USER32|GDI32' || true)
if [ -n "$bad" ]; then echo "WARNING: non-XP DLL import(s):"; echo "$bad"; else echo "imports: XP system DLLs only ✓"; fi
