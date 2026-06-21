# gcal-emu — synthetic Google test-board for the らき☆マス launcher

Fires the launcher's **calendar** (`gcal.exe`/`gcalcore.dll`) and **mail** (`Launch.exe`) speech
bubbles on command, so every translated bubble can be made to render + checked for overflow — with no
real Google account. Stdlib Python 3, one process: an HTTP server (ClientLogin + the two Atom feeds)
plus a tiny POP3 server. Protocol RE'd from the binaries; full notes in
[`../../docs/next-builds.md`](../../docs/next-builds.md) §"Build 1".

The launcher reaches us because XP's `hosts` redirects `www.google.com` → this host. The **GData feeds
are plain `http://` on :80** (this server). ⚠️ **CORRECTED 2026-06-22 by live-test: `/accounts/ClientLogin`
is HTTPS** — gcal.exe opens TLS for the login (WinINet `12157` secure-channel error otherwise). So a full
run also needs an **HTTPS `:443` endpoint** for `www.google.com` with an **XP-trusted self-signed cert +
XP-SP3-era TLS** (TLS1.0 + AES-CBC) — **not yet built** (this server is HTTP-only). Details:
[`../../docs/re-notes.md`](../../docs/re-notes.md) §Session 2.

## Bubbles ↔ scenarios

| bubble | scenario | what the board does |
|---|---|---|
| `SerifCallenderSchedule` | `calendar=schedule` | event feed returns ≥1 event anchored to "today" |
| `SerifCallenderNone` | `calendar=none` | event feed returns empty |
| `SerifCallenderError` | `calendar=error` | ClientLogin 403 + feeds 403 |
| `SerifCallenderNoAccount` | — | **app-side**: blank the GCal ID in `gcal.ini` (no server call) |
| `SerifMailCheck` | `mail=check` | POP3 `STAT` → `+OK n …` (n>0, default 3) |
| `SerifMailNone` | `mail=none` | POP3 `STAT` → `+OK 0 0` |
| `SerifMailError` | `mail=error` / `mail=refuse` | `PASS` → `-ERR` / drop the TCP connection |

## Run

> ⚠️ **Run on a SEPARATE always-on LAN box, not the Time Machine courier** — that box runs one OS at
> a time, so its NixOS is offline while XP is booted (and XP reuses its NIC/lease). Needs **port 80
> free**; XP's hosts points `www.google.com` at *this* box's IP.

```sh
# the emulator host (separate always-on LAN box): bind :80 + :110 (needs root for :80)
sudo python3 gcal_emu.py --scenario calendar=schedule,mail=check

# unprivileged self-test
python3 gcal_emu.py --http 8080 --pop 1110 --scenario calendar=none
```

**Flip the bubble live** (no restart) — the control file is re-read on every request:

```sh
echo calendar=none  > scenario.conf      # next calendar check → SerifCallenderNone
echo mail=error     > scenario.conf       # next mail check     → SerifMailError
```

Knobs (env or `scenario.conf`, `key=value`): `calendar`, `mail`, `mailcount`, `events`
(`;`-separated titles that fill `<%SCHEDULE%>`), `calname`, `account`, `tzoffset` (default `+09:00`).

## XP side — point the launcher at the board

1. `C:\WINDOWS\system32\drivers\etc\hosts` → add `<emu-host-ip>  www.google.com` (the separate box
   running this emulator — **not** the timemachine, which *is* XP while XP runs). The probe's
   `xp-probe.sh hosts on <ip>` does this for you. ⚠️ Also blackholes *real* google.com browsing on XP —
   fine for a retro box; remove the line to restore.
2. The launcher's right-click menu: `(&M)` = Mail check, `(&C)` = Calendar check.
3. Calendar account: `…\launcher\gcal.ini` needs a non-blank GCal ID (any value) or you get
   `SerifCallenderNoAccount` before any server call. Blank it on purpose to test that bubble.

## The request logger — lock the responses after the first real-XP run

Every HTTP request (method/path/**query**/headers/body) and every POP3 command is logged verbatim to
stdout **and** `gcal-emu.log`. The first real-XP calendar check captures the **exact** event-feed URL
the binary builds from the `<link href=>` we feed it, plus any `start-min`/`start-max` window — so we
can confirm/lock the Atom we return. The emulator already anchors `schedule` events to the requested
`start-min` day (else server-today), so a hit is guaranteed regardless of XP's clock.

## Status

Self-tested on all scenarios (curl + a POP3 client) 2026-06-21. **Not yet** validated against the
real `gcal.exe` — that's the first cold-loop run via the
[XP remote probe](../../../retro-hardware/projects/xp-remote-probe/). Open: confirm the binary's
actual event-feed query + that `gd:when@startTime` parses as expected (watch the log on first run).
