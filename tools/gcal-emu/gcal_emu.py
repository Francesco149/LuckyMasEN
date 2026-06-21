#!/usr/bin/env python3
"""
gcal_emu.py — synthetic Google-server test-board for the らき☆マス launcher.

Drives the launcher's **calendar** (`gcal.exe` / `gcalcore.dll`) and **mail**
(`Launch.exe`) speech bubbles on command, so every translated bubble can be made
to render + checked for overflow without a real Google account.

Wire format (RE'd from the binaries, all plain `http://` — see docs/next-builds.md):
  CALENDAR (MFC WinINet, host www.google.com, HTTP/1.0):
    POST /accounts/ClientLogin
         body  Email=%s&Passwd=%s&service=cl&source=sygnas-gcal-0.1
         reply SID=..\nLSID=..\nAuth=<token>\n            (client only reads Auth=)
    GET  /calendar/feeds/default/allcalendars/full[/]      Atom calendar LIST
         -> one <entry> with <title type='text'>, gCal:color, and a <link href=>
            pointing at the event feed.
    GET  <that href>  (…/private/full)                     Atom EVENT feed
         -> <entry>s with gd:when@startTime, gd:where, <title>. >=1 entry =>
            SerifCallenderSchedule (titles fill <%SCHEDULE%>); empty =>
            SerifCallenderNone. ClientLogin error / feed 403,500 => SerifCallenderError.
    GET  /calendar/event?action=TEMPLATE&dates=…           add-event deep-link (browser)
  MAIL (POP3, Launch.exe):  USER %s / PASS %s / STAT -> +OK <n> <size>
         n>0 => SerifMailCheck, n=0 => SerifMailNone, login refused => SerifMailError.

The launcher reaches us because XP's hosts file redirects `www.google.com` ->
this host (the courier). No HTTPS, no cert — the client speaks port-80 HTTP only.

Two knobs:
  * SCENARIO selector — env + a control file re-read on EVERY request, so you can
    flip the bubble live (`echo calendar=none > scenario.conf`) with no restart.
  * request LOGGER — every HTTP request (method/path/query/headers/body) and POP3
    command is logged verbatim, so the first real-XP run captures the exact
    event-feed URL/params the binary sends and we can lock the responses.

Stdlib only (py3.11+ for datetime.fromisoformat offset parsing). Run on the courier.

Usage:
  sudo python3 gcal_emu.py                         # :80 + :110, scenario from env/file
  python3 gcal_emu.py --http 8080 --pop 1110       # unprivileged, for self-test
  python3 gcal_emu.py --scenario calendar=none,mail=error
  GCAL_EMU_CAL=schedule GCAL_EMU_MAIL=check python3 gcal_emu.py
Live flip (while running): edit ./scenario.conf  (key=value lines: calendar=, mail=, …)
"""
import argparse, os, socket, socketserver, sys, threading
from datetime import datetime, date, time as dtime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# ---- config (env defaults; CLI + control-file override) ------------------------
CFG = {
    'calendar': os.environ.get('GCAL_EMU_CAL', 'schedule'),   # schedule|none|error
    'mail':     os.environ.get('GCAL_EMU_MAIL', 'check'),     # check|none|error
    'account':  os.environ.get('GCAL_EMU_ACCOUNT', 'test@example.com'),
    'calname':  os.environ.get('GCAL_EMU_CALNAME', 'Test Calendar'),
    'tzoffset': os.environ.get('GCAL_EMU_TZ', '+09:00'),      # JST; matches the JP box
    # ';'-separated event titles for the 'schedule' scenario (fill <%SCHEDULE%>)
    'events':   os.environ.get('GCAL_EMU_EVENTS', 'Dentist;Lunch with Konata;Buy doujinshi'),
    'mailcount': os.environ.get('GCAL_EMU_MAILCOUNT', '3'),   # n for mail=check
}
SCENARIO_FILE = os.environ.get('GCAL_EMU_SCENARIO_FILE', 'scenario.conf')
LOG_FILE = os.environ.get('GCAL_EMU_LOG', 'gcal-emu.log')
_log_lock = threading.Lock()

def log(msg):
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    with _log_lock:
        print(line, flush=True)
        try:
            with open(LOG_FILE, 'a') as f:
                f.write(line + '\n')
        except OSError:
            pass

def scenario():
    """env/CLI defaults (CFG) overlaid with the control file, re-read per request."""
    s = dict(CFG)
    try:
        with open(SCENARIO_FILE) as f:
            for ln in f:
                ln = ln.strip()
                if ln and not ln.startswith('#') and '=' in ln:
                    k, v = ln.split('=', 1)
                    s[k.strip()] = v.strip()
    except OSError:
        pass
    return s

# ---- Atom builders -------------------------------------------------------------
ATOM_NS = ("xmlns='http://www.w3.org/2005/Atom' "
           "xmlns:gd='http://schemas.google.com/g/2005' "
           "xmlns:gCal='http://schemas.google.com/gCal/2005'")

def xesc(s):
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
             .replace('"', '&quot;'))

def allcalendars_feed(s):
    """Atom calendar LIST: one entry whose <link href=> is the event feed URL."""
    feed_href = f"http://www.google.com/calendar/feeds/{s['account']}/private/full"
    return (f"<?xml version='1.0' encoding='UTF-8'?>\n"
            f"<feed {ATOM_NS}>\n"
            f"  <title type='text'>Calendar List</title>\n"
            f"  <entry>\n"
            f"    <title type='text'>{xesc(s['calname'])}</title>\n"
            f"    <link rel='alternate' type='application/atom+xml' href='{xesc(feed_href)}'/>\n"
            f"    <gCal:color value='#2952A3'/>\n"
            f"    <gCal:accesslevel value='owner'/>\n"
            f"    <gCal:selected value='true'/>\n"
            f"  </entry>\n"
            f"</feed>\n")

def _anchor_date(qs):
    """The day the launcher is asking about: GData start-min if present, else today."""
    sm = qs.get('start-min', [None])[0]
    if sm:
        try:
            return datetime.fromisoformat(sm.replace('Z', '+00:00')).date()
        except ValueError:
            pass
    return date.today()

def events_feed(s, qs):
    """Atom EVENT feed. >=1 entry => SerifCallenderSchedule, anchored to 'today'."""
    d = _anchor_date(qs)
    titles = [t.strip() for t in s['events'].split(';') if t.strip()]
    slots = [(9, 0, 10, 0), (12, 30, 13, 30), (15, 0, 16, 0), (18, 0, 19, 0)]
    rows = []
    for i, t in enumerate(titles):
        sh, sm, eh, em = slots[i % len(slots)]
        st = f"{d.isoformat()}T{sh:02d}:{sm:02d}:00.000{s['tzoffset']}"
        et = f"{d.isoformat()}T{eh:02d}:{em:02d}:00.000{s['tzoffset']}"
        rows.append(
            f"  <entry>\n"
            f"    <title type='text'>{xesc(t)}</title>\n"
            f"    <content type='text'>{xesc(t)}</content>\n"
            f"    <gd:when startTime='{st}' endTime='{et}'/>\n"
            f"    <gd:where valueString='Akihabara'/>\n"
            f"    <gd:eventStatus value='http://schemas.google.com/g/2005#event.confirmed'/>\n"
            f"  </entry>\n")
    return (f"<?xml version='1.0' encoding='UTF-8'?>\n"
            f"<feed {ATOM_NS}>\n"
            f"  <title type='text'>{xesc(s['calname'])}</title>\n"
            + ''.join(rows) + "</feed>\n")

# ---- HTTP server (ClientLogin + the two feeds + the deep-link) -----------------
class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'          # the client speaks HTTP/1.0
    server_version = 'gcal-emu/0.1'

    def log_message(self, *a):             # silence the stdlib access log; we log richer
        pass

    def _send(self, code, body, ctype='text/plain; charset=UTF-8'):
        data = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _logreq(self, body=b''):
        u = urlparse(self.path)
        hdrs = '; '.join(f'{k}: {v}' for k, v in self.headers.items())
        log(f"HTTP {self.command} {self.path}  from {self.client_address[0]}")
        log(f"  hdrs: {hdrs}")
        if u.query:
            log(f"  query: {u.query}")
        if body:
            log(f"  body: {body.decode('latin1')!r}")

    def _body(self):
        n = int(self.headers.get('Content-Length', 0) or 0)
        return self.rfile.read(n) if n else b''

    def do_POST(self):
        body = self._body()
        self._logreq(body)
        u = urlparse(self.path)
        s = scenario()
        if u.path == '/accounts/ClientLogin':
            if s['calendar'] == 'error':
                log("  -> ClientLogin 403 BadAuthentication (scenario calendar=error)")
                return self._send(403, "Error=BadAuthentication\n")
            log("  -> ClientLogin 200 Auth=<token>")
            return self._send(200, "SID=emu\nLSID=emu\nAuth=EMU_TEST_TOKEN\n")
        log(f"  -> 404 (unhandled POST {u.path})")
        self._send(404, "Not Found\n")

    def do_GET(self):
        self._logreq()
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        s = scenario()
        p = u.path.rstrip('/')
        if p == '/calendar/feeds/default/allcalendars/full':
            if s['calendar'] == 'error':
                log("  -> allcalendars 403 (scenario calendar=error)")
                return self._send(403, "Forbidden\n")
            log("  -> allcalendars list (1 calendar)")
            return self._send(200, allcalendars_feed(s),
                              ctype="application/atom+xml; charset=UTF-8")
        if p.startswith('/calendar/feeds/'):          # the event feed (any …/private/full)
            if s['calendar'] == 'error':
                log("  -> event feed 403 (scenario calendar=error)")
                return self._send(403, "Forbidden\n")
            n = 0 if s['calendar'] == 'none' else len(
                [t for t in s['events'].split(';') if t.strip()])
            log(f"  -> event feed ({n} events; scenario calendar={s['calendar']})")
            body = events_feed(s, qs) if n else (
                f"<?xml version='1.0' encoding='UTF-8'?>\n<feed {ATOM_NS}>\n"
                f"  <title type='text'>{xesc(s['calname'])}</title>\n</feed>\n")
            return self._send(200, body, ctype="application/atom+xml; charset=UTF-8")
        if p == '/calendar/event':                    # add-event deep-link (opened in a browser)
            log("  -> add-event TEMPLATE deep-link hit")
            return self._send(200, "<html><body>gcal-emu: add-event template "
                                   "(no-op test stub)</body></html>", ctype='text/html')
        log(f"  -> 404 (unhandled GET {u.path})")
        self._send(404, "Not Found\n")

# ---- POP3 server (Launch.exe mail check) ---------------------------------------
class POP3Handler(socketserver.StreamRequestHandler):
    def handle(self):
        s = scenario()
        peer = self.client_address[0]
        if s['mail'] == 'refuse':                     # hard refuse: drop the connection
            log(f"POP3 connection from {peer} -> dropped (scenario mail=refuse)")
            return
        try:
            n = int(s['mailcount']) if s['mail'] == 'check' else 0
        except ValueError:
            n = 1
        size = n * 1024
        def send(line):
            log(f"POP3 -> {line}")
            self.wfile.write((line + '\r\n').encode('latin1'))
        log(f"POP3 connection from {peer} (scenario mail={s['mail']}, n={n})")
        send("+OK gcal-emu POP3 ready")
        authed_user = False
        while True:
            raw = self.rfile.readline()
            if not raw:
                break
            cmd = raw.decode('latin1').strip()
            log(f"POP3 <- {cmd!r}")
            verb = cmd.split(' ', 1)[0].upper() if cmd else ''
            if verb == 'USER':
                authed_user = True; send("+OK user accepted")
            elif verb == 'PASS':
                if s['mail'] == 'error':
                    send("-ERR [AUTH] authentication failed")  # => SerifMailError
                else:
                    send("+OK mailbox ready")
            elif verb == 'STAT':
                send(f"+OK {n} {size}")                # n>0 => Check, n=0 => None
            elif verb == 'LIST':
                send(f"+OK {n} messages ({size} octets)")
                for i in range(1, n + 1):
                    send(f"{i} 1024")
                send(".")
            elif verb == 'UIDL':
                send(f"+OK")
                for i in range(1, n + 1):
                    send(f"{i} msg{i:04d}")
                send(".")
            elif verb == 'CAPA':
                send("-ERR no capabilities")
            elif verb == 'QUIT':
                send("+OK bye"); break
            elif verb == 'NOOP':
                send("+OK")
            else:
                send("-ERR unknown command")
        _ = authed_user

class ThreadingPOP3(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

# ---- main ----------------------------------------------------------------------
def apply_scenario_arg(arg):
    for kv in arg.split(','):
        if '=' in kv:
            k, v = kv.split('=', 1)
            CFG[k.strip()] = v.strip()

def main(argv):
    ap = argparse.ArgumentParser(description="synthetic gcal/mail test-board for the らき☆マス launcher")
    ap.add_argument('--http', type=int, default=int(os.environ.get('GCAL_EMU_HTTP_PORT', 80)))
    ap.add_argument('--pop',  type=int, default=int(os.environ.get('GCAL_EMU_POP_PORT', 110)))
    ap.add_argument('--bind', default=os.environ.get('GCAL_EMU_BIND', '0.0.0.0'))
    ap.add_argument('--scenario', help="seed scenario, e.g. calendar=none,mail=error")
    ap.add_argument('--no-pop', action='store_true', help="skip the POP3 server")
    args = ap.parse_args(argv)
    if args.scenario:
        apply_scenario_arg(args.scenario)

    s = scenario()
    log("=" * 70)
    log(f"gcal-emu starting: http={args.bind}:{args.http} pop={args.bind}:{args.pop}")
    log(f"scenario: calendar={s['calendar']} mail={s['mail']}  "
        f"(control file: {os.path.abspath(SCENARIO_FILE)})")
    log(f"log file: {os.path.abspath(LOG_FILE)}")
    log("XP must resolve www.google.com -> this host (hosts redirect). HTTP/1.0, no TLS.")
    log("bubbles: calendar=schedule|none|error  mail=check|none|error|refuse  "
        "(NoAccount = blank gcal.ini app-side, no server call)")
    log("=" * 70)

    httpd = ThreadingHTTPServer((args.bind, args.http), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    pop = None
    if not args.no_pop:
        pop = ThreadingPOP3((args.bind, args.pop), POP3Handler)
        threading.Thread(target=pop.serve_forever, daemon=True).start()
    try:
        t.join()
    except KeyboardInterrupt:
        log("shutting down")
        httpd.shutdown()
        if pop:
            pop.shutdown()
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
