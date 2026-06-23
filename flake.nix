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
    in {
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
