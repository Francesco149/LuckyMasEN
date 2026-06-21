# originals/ — RE input only, **never redistributed**

This directory holds the **owner's own copy** of the SYGNAS 「らき☆マス」(Lucky☆Mas) disc and
its installed payload (the MinkIt mascot engine + the sub-apps), used **solely as
reverse-engineering input** on the owner's own machines.

**Everything here except this README is `.gitignore`d.** No original SYGNAS file is committed,
pushed, or shipped. The project's deliverable is a **patch + tooling** that a user applies to
*their own* copy — the fan-translation / ROM-hack model. See the project
[README](../README.md) and the upstream scope doc in
`retro-hardware/projects/minkit-en-patch/`.

Expected contents (all ignored):

- `disc/` — the four files off `LuckyMaster.iso` (`autorun.inf`, `rakimas.ico`, `setup.exe`,
  `お読みください.txt`).
- `installed/` — the payload cracked out of `setup.exe` (or rsync'd from the XP install at
  `C:\Program Files\SYGNAS\らき―copy\`): `MinkIt.exe` / `MinkIt.dll` / `MinkIt.ini`, the
  `*.mink` character containers, the screensavers and the sub-apps.

Source of truth for the durable copy: the retro-kit master at
`wslop:/mnt/c/Users/headpats/Documents/retro-machines/z97x-timemachine/retro-drivers/xp/customization/`.
