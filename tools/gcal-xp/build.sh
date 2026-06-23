#!/usr/bin/env bash
# build.sh — cross-compile gcalsrv.exe for Windows XP (i686, subsystem 5.1).
#
# The server is C (Winsock sockets + Schannel TLS + POP3 framing) with the request
# logic in embedded Lua 5.4 (gcalsrv.lua). Links ws2_32/secur32/crypt32 + a static
# liblua.a compiled from the nix-pinned Lua source. The subsystem-version override +
# _WIN32_WINNT=0x0501 make the PE load on XP SP3; -static + the mcfgthreads lib dir
# keep the EXE importing ONLY XP system DLLs (the mcf threads code is dead-stripped —
# we use native CreateThread). -no-pie = fixed base. -mwindows = no console window.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; cd "$here"
CC=i686-w64-mingw32-gcc
AR=i686-w64-mingw32-ar

# Bring the cross toolchain on PATH from nix if needed (works in `nix develop` / any box with nix).
if ! command -v "$CC" >/dev/null 2>&1; then
  exec nix shell nixpkgs#pkgsCross.mingw32.buildPackages.gcc --command bash "$0" "$@"
fi

# --- embedded assets ---
[ -f cert_pfx.h ] || ./embed-pfx.sh     # cert (PKCS#12 has random salt → regen only if absent)
./embed-lua.sh                          # script (deterministic → always regen, stays in sync)

# --- Lua 5.4 static lib, compiled once from the nix-pinned source (cached) ---
LUADIR="$here/.luabuild/lua"
if [ ! -f "$here/.luabuild/liblua.a" ]; then
  SRC=$(nix build nixpkgs#lua5_4.src --no-link --print-out-paths | tail -1)
  mkdir -p "$here/.luabuild"
  [ -d "$LUADIR" ] || { tar xzf "$SRC" -C "$here/.luabuild"; mv "$here"/.luabuild/lua-5.4.* "$LUADIR"; }
  ( cd "$LUADIR/src"
    CORE="lapi lcode lctype ldebug ldo ldump lfunc lgc llex lmem lobject lopcodes lparser lstate lstring ltable ltm lundump lvm lzio"
    LIB="lauxlib lbaselib lcorolib ldblib liolib lmathlib loadlib loslib lstrlib ltablib lutf8lib linit"
    obj=""
    for f in $CORE $LIB; do "$CC" -O2 -c "$f.c" -o "$f.o"; obj="$obj $f.o"; done
    "$AR" rcs "$here/.luabuild/liblua.a" $obj
    echo "built liblua.a ($(echo $obj | wc -w) objects)" )
fi

MCF=$(nix build nixpkgs#pkgsCross.mingw32.windows.mcfgthreads --no-link --print-out-paths | tail -1)

"$CC" gcalsrv.c -o gcalsrv.exe \
  -O2 -s -mwindows -no-pie -static -static-libgcc \
  -I"$LUADIR/src" \
  -D_WIN32_WINNT=0x0501 \
  -Wall -Wextra -Wno-unused-parameter \
  -Wl,--major-subsystem-version=5,--minor-subsystem-version=1 \
  "$here/.luabuild/liblua.a" \
  -L"$MCF/lib" -lws2_32 -lsecur32 -lcrypt32 -luser32 -lshell32

echo "--- built $here/gcalsrv.exe ---"
ls -l gcalsrv.exe

# Sanity: the only imported DLLs must be XP system DLLs (no api-ms-win-*, no mcfgthread).
bad=$(i686-w64-mingw32-objdump -p gcalsrv.exe \
      | grep -i 'DLL Name' \
      | grep -ivE 'KERNEL32|WS2_32|Secur32|CRYPT32|msvcrt|ADVAPI32|USER32|GDI32|SHELL32' || true)
if [ -n "$bad" ]; then echo "WARNING: non-XP DLL import(s):"; echo "$bad"; else echo "imports: XP system DLLs only ✓"; fi
