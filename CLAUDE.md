# CLAUDE.md — LuckyMasterEN orientation

English fan-translation **patch + tooling** for SYGNAS 「らき☆マス」 (*Lucky☆Mas*, 2007 doujin
desktop-accessory pack) + an RE log for its in-house **MinkIt** mascot engine, and a **native
XP-local fake-Google server** so the launcher's calendar/mail mascots work with no Google account.

Read first: `README.md`, `docs/re-notes.md` (RE log), `docs/next-builds.md` (the build plan +
session log), `docs/mink-format.md` (container specs). Upstream scope:
`../retro-hardware/projects/minkit-en-patch/README.md`.

## Sibling repos (private home-lab — CLAUDE.md MAY point here; user-facing docs may NOT)
- **`../retro-hardware`** — the Windows XP "Time Machine" hardware build **and all the XP deploy/test ops
  for this project** (see the pointer section below). This is where you learn to run LuckyMas live on XP.
- **`../nix-lab`** — the home-lab NixOS flake (the deploy + cross-build hosts).

## Hard rule
Never commit or redistribute any SYGNAS original file. `originals/` is gitignored. We ship only a
delta + tooling that applies to the user's own disc copy. The `certs/` self-signed `www.google.com`
fixture is NOT a SYGNAS file and NOT a secret (a LAN-isolated fake-Google fixture) → committed on
purpose so the served cert == the cert installed in XP's Root, byte-for-byte.

## Deploy + test live on the XP box → see `../retro-hardware` (don't reinvent it here)
You don't deploy/drive XP from this repo — the full, current, private recipe lives in the hardware repo:
- **`../retro-hardware/projects/minkit-en-patch/`** — LuckyMas-specific ops: **`deploy-xp.sh`**
  (`probe`/`launcher`/`copy`/`server`/`hosts`/`launch`/`shot`/`winshot`; reads this repo's `out/patched` +
  `tools/gcal-xp/`, override `LM_REPO=`/`XP_IP=`), **`xp-ops-cheatsheet.md`** (the **agent-less** recipe —
  `netexec` exec + `smbclient` files + `iexec.exe` console GUI; the **boxes**, the **boot ladder**, gcalsrv
  lifecycle, silent SYSTEM cert install), **`OVERNIGHT-HANDOFF.md`** (the autonomous per-item test plan).
  ⚠️ **Screenshots:** BitBlt (`savescreenshotfull`/`win`) = **BLACK** when the monitor is off — the **q9650's
  CRT powers off** → do visual tests on **timemachine (LCD, JP locale)** via **PrtScn→clipboard**.
- **`../retro-hardware/HANDOFF.md`** + **`projects/xp-remote-probe/`** — fleet/access + the agent-less
  control stack (`iexec` GUI via `netexec --exec-method smbexec`; the old `xphttpd` :8099 agent is RETIRED).
  XP build: **`builds/time-machine-asbuilt.md`**.
- Gist: each XP box runs **one OS at a time** (reach it over SMB; offline while in its other OS). **q9650**
  = `10.0.10.134`, EN, no-WoL, CRT (capture-black); **timemachine** = `.113/.114/.115`, WoL-able, LCD, JP.
  EN install root `C:\Program Files\SYGNAS\LuckyMas\{copy,launcher,calc,wallpaper}`. Loop the owner in only
  for visual judgment a screenshot can't settle, or physical actions. **Everything specific lives in retro-hardware.**
- **Waking timemachine (WoL): wslop/WSL2 CANNOT send WoL** (NAT drops the broadcast) — **relay through `code`**
  (`ssh root@code`, LAN `10.0.10.53`): `WOL=$(ssh root@code 'sh -c "ls -d /nix/store/*wakeonlan*/bin/wakeonlan|head -1"'); ssh root@code "$WOL 74:d4:35:ea:6d:f2"`
  (wakeonlan isn't on code's PATH → glob the store). Then the courier is on the LAN at `10.0.10.115`; arm a
  one-shot XP boot: `ssh root@10.0.10.115 'grub-reboot "Windows XP (Crucial)" && systemctl reboot'`. Full
  ladder in retro-hardware `xp-ops-cheatsheet.md`. (Don't re-derive this — it's the standing recipe.)

## Building XP binaries (i686, XP subsystem)
Cross-compile with mingw-w64 via nix (works in `nix develop`):
```sh
nix shell nixpkgs#pkgsCross.mingw32.buildPackages.gcc --command \
  i686-w64-mingw32-gcc src.c -o out.exe -lws2_32 -O2 -s -mwindows \
  -D_WIN32_WINNT=0x0501 -Wl,--major-subsystem-version=5,--minor-subsystem-version=1
```
The `--*-subsystem-version=5.1` + `_WIN32_WINNT=0x0501` make the PE load on XP. Schannel/CryptoAPI
builds add `-lsecur32 -lcrypt32`.

## The gcal-xp native server (`tools/gcal-xp/`) — the current build
One self-contained Win32 EXE the user runs on their own XP box (`hosts: www.google.com → 127.0.0.1`)
so the mascots' calendar/mail work with no Google account:
- **HTTP feeds `:80`** (allcalendars list + event feed + add-event deep-link) + **POP3 `:110`** —
  plain Winsock.
- **HTTPS `/accounts/ClientLogin` `:443`** — **Schannel** (server + client are the same 2007 stack →
  period-accurate TLS by construction; no modern-TLS coercion). Cert = self-signed `www.google.com`
  (RSA-2048/SHA-1) embedded as a PFX (`cert_pfx.h`), installed into XP's **Root** in-process so
  WinINet trusts it.
- **Request logic + content in `gcalsrv.lua`** (Lua 5.4, embedded; an external `<exedir>\gcalsrv.lua`
  overrides + **hot-reloads** on save): user-editable **date-keyed `EVENTS`/`MAIL` tables** drive the
  bubbles (a working fake POP3 mailbox — STAT/LIST/UIDL/RETR/TOP). C↔Lua = `http_handle` + `pop3_event`.
- **Tray UI** (Open gcalsrv.lua / About / Close; `--no-tray` = headless for SMB-exec); Lua errors pop a
  message box. **`--install-cert`** writes the cert to `HKLM\…\SystemCertificates\Root` via the **registry
  store provider** (`CERT_STORE_PROV_REG`) — silent even run interactively (the SYSTEM store provider pops
  XP's protected-root modal; REPLACE_EXISTING = two prompts). The **installer
  auto-installs** it: `{app}\gcal-xp` + `{commonstartup}` autostart + silent cert trust ([Run]).
- **`tools/gcal-emu/gcal_emu.py`** is the protocol **oracle** (Python; retired as a deployed host,
  kept as the reference for the exact responses). Wire format + bubble↔scenario table:
  `docs/next-builds.md` §"Build 1"/§"Session 3".

## The reproducible patch (`patch/manifest.toml` + `tools/build_patch.py`)
Every file we patch goes through ONE pipeline → spec in `docs/patch-system.md`. `manifest.toml` is the
single source of truth (one entry per file + op + note; `active=false` = recorded-but-deferred);
`build_patch.py` mirrors `originals/installed/`→`out/patched/` (gitignored), applies ops, writes
`PATCH-LOG.txt`. Ops: `xvi`/`text_keys`/`text_subst`/`text_file`/`binpatch`/`asmpoke`/`pe_res`/`pak`/`img_text`/`mink_info`/`rename`/`rename_map`. Reproducible.
`pe_res` (`tools/pe_res.py`) **surgically** patches PE-resource menus/dialogs (lang 1041) + does geometry
overrides — **never `lief.write()`** (it rebuilds the PE and crashes XP). `binpatch` does size-preserving
NUL-terminated string replace: `wide=true` (UTF-16) | `encoding="cp932"` (SJIS, for JP drawn via `*A` APIs)
| latin1. `asmpoke` (`tools/build_patch.py`) is the **.text/.rdata surgeon** for what binpatch can't do —
same-size verified byte `poke`s (each asserts its `old` bytes) + `wstr` writes of UTF-16 literals into a
**mapped, verified-zero, unreferenced cave** (within a section's VirtualSize — NOT the file-align slack past it,
which is unmapped). Used to relocate gcal.exe's 3 custom-drawn toolbar labels to a cave + repoint the
`push offset` + bump the SetString counts / hit-rect x,w / TextOutW x immediates (`va`=virtual addr; no `lief`).
Find hardcoded JP with **`tools/scan_jp.py`** (`strings` can't see cp932). The `pak` op rebuilds the calc
`data.pak`: per-member `.nut` string `subs` (decode via the cracked LZSS — `sygnas_unpack.pak_decompress`/
`sygnas_repack.pak_compress` — find/replace, re-compress) + `gen="calc_png"` (retext the baked button-label
PNGs from the user's own images via `tools/calc_png.py`, MS PGothic). `img_text` retexts loose baked-text
images (the wallpaper section headers, same `calc_png` engine); `mink_info` retitles the MinkIt mascot
names (decode each `.mink` `info` chunk via the cracked third LZSS — `sygnas_*.mink_info_*`/`repack_mink` —
swap `Title=` → ASCII, re-compress; the strings the engine's Settings list + Preview show); `rename_map`
bulk-renames files by a substring map + rewrites refs in lockstep. **The translation surface is COMPLETE** —
all PE-resource UI, all hardcoded/runtime JP, gcal.exe's 3 custom-drawn toolbar buttons (更新/表示設定/動作設定 →
Refresh/View/Options via `asmpoke`), the themed calculators (`calmain.nut` + button PNGs), the
wallpaper picker (84 JPGs + HTML refs ASCII'd; 壁紙の設定方法/壁紙一覧/モニターサイズ header images retexted),
the 4 screensaver filenames (the rename relabels the engine `.scr`; the disc shipped them as **gutted
ScreenTime-for-Flash engine stubs** WITHOUT their content — a SYGNAS defect, not locale/our-patch — but the
EN build now **RESTORES** the working ones: `tools/screensaver_restore.py` extract-and-merges the missing
per-saver content + Flash 8 from SYGNAS's apology installers (SHA-256-pinned on archive.org, downloaded at
build, never committed) into `{sys}\<EN-name> dir\` next to our byte-identical `.scr`; see
`docs/screensaver-re.md`),
and the 5 MinkIt mascot Titles (Konata/
Kagami/Chihaya/Makoto/Yayoi) are EN. Held back (recorded, non-text): the `CreateFontA` facenames
(`ＭＳ Ｐゴシック`; fine when PGothic present — the installer bundles it), MFC/VERSIONINFO boilerplate, and
the textless `.mink` **a0/m0 sprite** codec (the `info` metadata codec is now cracked; a0/m0 carry no text).
End goal = **English installer re-wrapped from the user's own `setup.exe`** (ISCC under wine; consumes
`out/patched/`). **Locale rule** (goal #2): app-read text (Launch.ini, `.Xvi` serifs via `*A` APIs) =
**pure ASCII**; readme = UTF-8+BOM; HTML = UTF-8. **host→localhost** done in `gcalcore.dll`+`gcal.exe`
(binpatch) + cert CN=localhost — drop the XP `hosts` line. The `.mink`/`.scr`/wallpaper-JPG renames are
now ACTIVE; only the Launch.ini install-root path rewrite stays deferred (the installer pins `{app}` via `[INI]`).

## The one-command end-user builder (`tools/make_iso.py`) — cross-platform self-service
The packaged front-door: the user supplies only **their own disc `setup.exe`** + **their own MS PGothic**
and gets `out/LuckyMas-EN.iso` (+ `.zip`). One shared Python engine runs everywhere; pipeline =
`innoextract` (read the installed tree straight out of the user's setup.exe — no game install needed) →
`build_patch.py` → `screensaver_restore.py` (download+extract the 4 apology installers' working content +
Flash 8 into `out/patched/sys`; `--skip-screensavers` to opt out) →
`get_font.py` (`--font auto` finds it on Win/WSL) → `innounp -x -y -b -m` (the OG
wizard art; `-y -b` or it hangs on the overwrite prompt under wine) → **ISCC** → ISO via **pycdlib else
xorriso**. Platform-aware: ISCC + innounp run **native on Windows, under wine on Linux**. The freeware
tools (Inno Setup 5.6.1, innounp 0.50, innoextract 1.9) are resolved explicit-flag → PATH/known-loc →
cache → **pinned + SHA-256 auto-download** (`~/.cache/luckymasen`; pins in `make_iso.py` PINS).
- **Front-doors** (owner chose per-OS native bundles): **Windows** = `installer/windows/build.bat`
  (+`bootstrap_python.ps1`) — keeps a private embeddable Python so it ignores the Store-alias python stub,
  runs ISCC **natively (no wine)**; the zip is assembled from Linux by **`tools/make_windows_bundle.sh`**
  (toolchain + prebuilt `gcalsrv.exe` + a cache pre-seeded with the Windows tool builds → offline). **Linux**
  = **`nix run .#iso`** (flake app `apps.iso`; local checkout or remote-staged from `${self}`; self-builds
  `gcalsrv.exe` via build.sh if absent) **and a tarball** via `tools/make_linux_bundle.sh`. **Validated
  end-to-end on real Win10 (native ISCC) + Linux** → byte-valid 48 MB ISO. `gcalsrv.exe` is OUR
  redistributable artifact (ship prebuilt; no mingw for the user). Output-on-Windows console must stay
  ASCII/encoding-safe (cp1252). Guide: `docs/end-user-build.md`.
- **CI**: `.github/workflows/nightly.yml` builds gcalsrv + both bundles (lean `nix shell`, NOT the full
  devShell) on every push to master and moves the **`nightly`** prerelease tag to the built commit with the
  latest artifacts. Test Windows builds natively on this WSL box's host via interop (`cmd.exe`, `/mnt/c`).

## Conventions
- Persist cross-session **orientation in this CLAUDE.md**; the running RE/build narrative in
  `docs/re-notes.md` + `docs/next-builds.md`. Windows-bound `.txt`/`.reg`/`.cmd` files = CRLF.
- `nix develop` drops into the RE/TL shell (ghidra, rizin, wrestool, wine, qemu, python+lief…).
