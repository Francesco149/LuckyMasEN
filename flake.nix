{
  description = "LuckyMasterEN — RE + English fan-translation toolchain for SYGNAS 「らき☆マス」(Lucky☆Mas) and its in-house MinkIt desktop-mascot engine (2007). Tooling only — original copyrighted files are never redistributed (see ./originals/README.md).";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};

      # Python env for the .mink-format RE and PE poking.
      py = pkgs.python3.withPackages (ps: with ps; [
        pillow      # decode/encode sprite frames (BMP/PNG)
        numpy       # raw pixel / byte-grid wrangling
        construct   # declarative binary-format parsing — model the .mink container
        lief        # parse/edit PE (resources, imports, strings) programmatically
      ]);
      # `nix run .#iso -- --setup <disc-setup.exe> --font auto` — the Linux one-command
      # front-door (run from a clone of this repo). Provides every host tool the engine
      # needs; ISCC + innounp run under wine, innoextract/xorriso are native. The freeware
      # build tools are still auto-fetched (pinned + sha256) by make_iso.py into the cache.
      iso-app = pkgs.writeShellApplication {
        name = "luckymas-iso";
        runtimeInputs = with pkgs; [
          py innoextract wineWowPackages.stable xorriso libarchive cabextract
          curl p7zip nix bash coreutils gnutar gzip gnused gnugrep which
        ];
        text = ''
          orig="$PWD"
          extra=()
          if [ -f tools/make_iso.py ]; then
            cd "$orig"                       # run in-place from a local checkout (out/ lands here)
          else
            # remote (`nix run github:…#iso`): stage this flake's toolchain to a writable work dir,
            # put the built ISO back in the caller's directory.
            work="$orig/luckymas-build"
            echo "staging the toolchain to $work …" >&2
            mkdir -p "$work"
            cp -rT --no-preserve=mode,ownership "${self}" "$work"
            cd "$work"
            extra=(--out "$orig/out")
          fi
          # gcalsrv.exe is our own redistributable artifact; build it once if absent (mingw via nix).
          if [ ! -f tools/gcal-xp/gcalsrv.exe ]; then
            echo "gcalsrv.exe missing — building it once (mingw cross-compile via nix)…" >&2
            bash tools/gcal-xp/build.sh
          fi
          exec python3 tools/make_iso.py "''${extra[@]}" "$@"
        '';
      };
    in {
      apps.${system}.iso   = { type = "app"; program = "${iso-app}/bin/luckymas-iso"; };
      packages.${system}.iso = iso-app;

      devShells.${system}.default = pkgs.mkShell {
        name = "luckymaster-en";
        packages = with pkgs; [
          # — disassembly / decompilation —
          ghidra            # primary decompiler for MinkIt.exe / MinkIt.dll
          rizin cutter      # CLI + GUI RE (rizin engine)
          # — PE / binary inspection —
          pev               # readpe / pescan — PE headers, sections, imports
          icoutils          # wrestool: list/extract PE resources (menu/dialog/string-table/icons)
          binutils          # objdump, nm, strings
          file hexyl imhex  # identify · pretty-hex · format-RE workbench (pattern language)
          upx               # detect/unpack UPX (README: the binaries may be packed)
          # — sprite / image —
          imagemagick
          # — binary patching / diffs (route B: static patcher) —
          xdelta flips      # xdelta3 + IPS/BPS
          # — locale-shim + run loops —
          wineWowPackages.stable winetricks   # inner test loop (Win32, ANSI cp932)
          qemu                                 # validation-VM loop + qemu-img / qemu-nbd
          # — archives / installer cracking —
          p7zip cabextract innoextract unzip
          libarchive        # bsdtar — unpack the innounp .rar during tool auto-fetch (tools/make_iso.py)
          curl              # tool auto-download (pinned + sha256) for make_iso.py
          xorriso           # ISO9660/Joliet writer — the patched-disc output when pycdlib is absent (make_iso.py)
          # — python format-RE env —
          py
          # — misc —
          ripgrep jq
        ];

        shellHook = ''
          echo "LuckyMasterEN — RE + fan-TL toolchain"
          echo "  decompile: ghidra · rizin/cutter      resources: wrestool (icoutils) · pev · imhex"
          echo "  run/loop:  wine · qemu                 patch: xdelta3 · flips      py: construct/lief/pillow"
          echo "  NOTE: originals/ is gitignored — never commit or redistribute any SYGNAS file."
        '';
      };
    };
}
