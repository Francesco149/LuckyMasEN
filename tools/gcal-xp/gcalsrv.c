/* gcalsrv.c - native XP-local fake-Google server for the らき☆マス launcher.
 *
 * One self-contained Win32 EXE the user runs on their own Windows XP box so the
 * launcher's calendar (gcal.exe / gcalcore.dll) and mail (Launch.exe) mascots
 * work with NO Google account. XP's hosts file points www.google.com ->
 * 127.0.0.1 and this server answers as Google:
 *
 *   :80   HTTP/1.0  GData feeds      (allcalendars list + event feed + add-event)
 *   :443  HTTPS     /accounts/ClientLogin   (TLS via Schannel - period-accurate:
 *                                            server Schannel <-> client WinINet,
 *                                            the same 2007 stack)
 *   :110  POP3      USER/PASS/STAT          (Launch.exe mail check)
 *
 * The cert is a self-signed www.google.com leaf (RSA-2048/SHA-1) carried inside
 * the EXE as a PKCS#12 blob (cert_pfx.h). On startup the server PFXImportCertStore()s
 * it for Schannel's server credential and installs the public cert into XP's Root
 * so WinINet trusts the TLS endpoint.
 *
 * Protocol oracle: tools/gcal-emu/gcal_emu.py (the responses here are ported from it).
 * Wire format + bubble<->scenario table: docs/next-builds.md.
 *
 * Build (i686, XP subsystem) - see build.sh:
 *   i686-w64-mingw32-gcc gcalsrv.c -o gcalsrv.exe -lws2_32 -lsecur32 -lcrypt32 \
 *     -O2 -s -mwindows -D_WIN32_WINNT=0x0501 \
 *     -Wl,--major-subsystem-version=5,--minor-subsystem-version=1
 */
#define WIN32_LEAN_AND_MEAN
#define SECURITY_WIN32
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0501
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <wincrypt.h>
#include <schannel.h>
#include <security.h>
#include <sspi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <ctype.h>

/* embedded www.google.com PKCS#12 (CERT_PFX / CERT_PFX_LEN / CERT_PFX_PASS) */
#include "cert_pfx.h"

#define DEF_HTTP_PORT  80
#define DEF_HTTPS_PORT 443
#define DEF_POP3_PORT  110
#define RECV_TIMEOUT_MS 20000
#define TLS_INBUF_CAP  (32 * 1024)
#define HTTP_REQ_CAP   (32 * 1024)

/* ---- globals ----------------------------------------------------------------- */
static int   g_http_port  = DEF_HTTP_PORT;
static int   g_https_port = DEF_HTTPS_PORT;
static int   g_pop_port   = DEF_POP3_PORT;
static int   g_tls_ok     = 0;          /* set once Schannel creds are acquired */
static char  g_exedir[MAX_PATH];
static char  g_logpath[MAX_PATH];
static char  g_inipath[MAX_PATH];
static CRITICAL_SECTION g_loglock;

static CredHandle    g_hCred;           /* Schannel server credential (shared, read-only) */
static PCCERT_CONTEXT g_pCert = NULL;   /* our www.google.com cert (with private key) */

/* ---- logging ----------------------------------------------------------------- */
static void logln(const char *fmt, ...) {
    char line[2048];
    SYSTEMTIME st; GetLocalTime(&st);
    int n = _snprintf(line, sizeof(line), "%04d-%02d-%02d %02d:%02d:%02d ",
                      st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
    if (n < 0) n = 0;
    va_list ap; va_start(ap, fmt);
    _vsnprintf(line + n, sizeof(line) - n - 2, fmt, ap);
    va_end(ap);
    line[sizeof(line) - 2] = 0;
    strcat(line, "\n");
    EnterCriticalSection(&g_loglock);
    FILE *f = fopen(g_logpath, "a");
    if (f) { fputs(line, f); fclose(f); }
    LeaveCriticalSection(&g_loglock);
}

/* ---- tiny dynamic string builder --------------------------------------------- */
struct sb { char *p; int len, cap; };
static void sb_init(struct sb *b) { b->cap = 4096; b->len = 0; b->p = malloc(b->cap); if (b->p) b->p[0] = 0; }
static void sb_ensure(struct sb *b, int extra) {
    if (b->len + extra + 1 <= b->cap) return;
    while (b->len + extra + 1 > b->cap) b->cap *= 2;
    b->p = realloc(b->p, b->cap);
}
static void sb_add(struct sb *b, const char *s, int n) {
    if (!b->p) return;
    sb_ensure(b, n);
    memcpy(b->p + b->len, s, n); b->len += n; b->p[b->len] = 0;
}
static void sb_adds(struct sb *b, const char *s) { sb_add(b, s, (int)strlen(s)); }
static void sb_addf(struct sb *b, const char *fmt, ...) {
    char tmp[2048]; va_list ap; va_start(ap, fmt);
    int n = _vsnprintf(tmp, sizeof(tmp), fmt, ap); va_end(ap);
    if (n < 0) n = (int)strlen(tmp);
    if (n > (int)sizeof(tmp)) n = (int)sizeof(tmp);
    sb_add(b, tmp, n);
}

/* ---- config (scenario), re-read per request ---------------------------------- */
struct cfg {
    char calendar[16];   /* schedule | none | error */
    char mail[16];       /* check | none | error | refuse */
    char account[128];
    char calname[128];
    char tzoffset[16];
    char events[1024];   /* ';'-separated titles */
    int  mailcount;
};
static void cfg_defaults(struct cfg *c) {
    strcpy(c->calendar, "schedule");
    strcpy(c->mail, "check");
    strcpy(c->account, "test@example.com");
    strcpy(c->calname, "Test Calendar");
    strcpy(c->tzoffset, "+09:00");
    strcpy(c->events, "Dentist;Lunch with Konata;Buy doujinshi");
    c->mailcount = 3;
}
static void cfg_set(struct cfg *c, const char *k, const char *v) {
    if      (!_stricmp(k, "calendar"))  { strncpy(c->calendar, v, sizeof(c->calendar) - 1); }
    else if (!_stricmp(k, "mail"))      { strncpy(c->mail, v, sizeof(c->mail) - 1); }
    else if (!_stricmp(k, "account"))   { strncpy(c->account, v, sizeof(c->account) - 1); }
    else if (!_stricmp(k, "calname"))   { strncpy(c->calname, v, sizeof(c->calname) - 1); }
    else if (!_stricmp(k, "tzoffset"))  { strncpy(c->tzoffset, v, sizeof(c->tzoffset) - 1); }
    else if (!_stricmp(k, "events"))    { strncpy(c->events, v, sizeof(c->events) - 1); }
    else if (!_stricmp(k, "mailcount")) { c->mailcount = atoi(v); }
}
static void cfg_load(struct cfg *c) {
    cfg_defaults(c);
    FILE *f = fopen(g_inipath, "r");
    if (!f) return;
    char ln[1200];
    while (fgets(ln, sizeof(ln), f)) {
        char *p = ln; while (*p == ' ' || *p == '\t') p++;
        if (*p == '#' || *p == ';' || *p == '\r' || *p == '\n' || *p == 0) continue;
        char *eq = strchr(p, '=');
        if (!eq) continue;
        *eq = 0;
        char *k = p, *v = eq + 1;
        /* trim key trailing ws */
        char *ke = k + strlen(k); while (ke > k && (ke[-1] == ' ' || ke[-1] == '\t')) *--ke = 0;
        /* trim value ws + EOL */
        while (*v == ' ' || *v == '\t') v++;
        char *ve = v + strlen(v); while (ve > v && (ve[-1] == '\r' || ve[-1] == '\n' || ve[-1] == ' ' || ve[-1] == '\t')) *--ve = 0;
        cfg_set(c, k, v);
    }
    fclose(f);
}

/* ---- helpers ----------------------------------------------------------------- */
/* XML-escape src into dst (bounded); returns dst */
static char *xesc(const char *src, char *dst, int cap) {
    int o = 0;
    for (; *src && o < cap - 7; src++) {
        switch (*src) {
            case '&': memcpy(dst + o, "&amp;", 5);  o += 5; break;
            case '<': memcpy(dst + o, "&lt;", 4);   o += 4; break;
            case '>': memcpy(dst + o, "&gt;", 4);   o += 4; break;
            case '"': memcpy(dst + o, "&quot;", 6); o += 6; break;
            default:  dst[o++] = *src;
        }
    }
    dst[o] = 0;
    return dst;
}

/* The day the launcher asks about: GData start-min if present, else local today. */
static void anchor_date(const char *query, int *y, int *m, int *d) {
    SYSTEMTIME st; GetLocalTime(&st);
    *y = st.wYear; *m = st.wMonth; *d = st.wDay;
    if (!query) return;
    const char *p = strstr(query, "start-min=");
    if (!p) return;
    p += 10;
    int yy, mm, dd;
    if (sscanf(p, "%4d-%2d-%2d", &yy, &mm, &dd) == 3 && mm >= 1 && mm <= 12 && dd >= 1 && dd <= 31) {
        *y = yy; *m = mm; *d = dd;
    }
}

/* split ';'-separated, space-trimmed, non-empty titles into out[]; returns count */
static int split_events(const char *events, char out[][256], int maxn) {
    int n = 0; const char *p = events;
    while (*p && n < maxn) {
        while (*p == ' ') p++;
        const char *start = p;
        while (*p && *p != ';') p++;
        const char *end = p;
        while (end > start && end[-1] == ' ') end--;
        int len = (int)(end - start); if (len > 255) len = 255;
        if (len > 0) { memcpy(out[n], start, len); out[n][len] = 0; n++; }
        if (*p == ';') p++;
    }
    return n;
}

#define ATOM_NS \
    "xmlns='http://www.w3.org/2005/Atom' " \
    "xmlns:gd='http://schemas.google.com/g/2005' " \
    "xmlns:gCal='http://schemas.google.com/gCal/2005'"

/* Atom calendar LIST: one <entry> whose <link href=> is the event-feed URL. */
static void build_allcalendars(struct sb *b, const struct cfg *c) {
    char cal[256], href[512], hrefe[600];
    xesc(c->calname, cal, sizeof(cal));
    _snprintf(href, sizeof(href),
              "http://www.google.com/calendar/feeds/%s/private/full", c->account);
    xesc(href, hrefe, sizeof(hrefe));
    sb_adds(b, "<?xml version='1.0' encoding='UTF-8'?>\n");
    sb_addf(b, "<feed %s>\n", ATOM_NS);
    sb_adds(b, "  <title type='text'>Calendar List</title>\n");
    sb_adds(b, "  <entry>\n");
    sb_addf(b, "    <title type='text'>%s</title>\n", cal);
    sb_addf(b, "    <link rel='alternate' type='application/atom+xml' href='%s'/>\n", hrefe);
    sb_adds(b, "    <gCal:color value='#2952A3'/>\n");
    sb_adds(b, "    <gCal:accesslevel value='owner'/>\n");
    sb_adds(b, "    <gCal:selected value='true'/>\n");
    sb_adds(b, "  </entry>\n</feed>\n");
}

/* Atom EVENT feed. >=1 entry => SerifCallenderSchedule, anchored to "today". */
static void build_events(struct sb *b, const struct cfg *c, const char *query) {
    static const int slots[4][4] = { {9,0,10,0}, {12,30,13,30}, {15,0,16,0}, {18,0,19,0} };
    int y, m, d; anchor_date(query, &y, &m, &d);
    char cal[256]; xesc(c->calname, cal, sizeof(cal));
    sb_adds(b, "<?xml version='1.0' encoding='UTF-8'?>\n");
    sb_addf(b, "<feed %s>\n", ATOM_NS);
    sb_addf(b, "  <title type='text'>%s</title>\n", cal);

    char titles[64][256];
    int nt = split_events(c->events, titles, 64);
    for (int i = 0; i < nt; i++) {
        const int *s = slots[i % 4];
        char te[512]; xesc(titles[i], te, sizeof(te));
        sb_adds(b, "  <entry>\n");
        sb_addf(b, "    <title type='text'>%s</title>\n", te);
        sb_addf(b, "    <content type='text'>%s</content>\n", te);
        sb_addf(b, "    <gd:when startTime='%04d-%02d-%02dT%02d:%02d:00.000%s' "
                   "endTime='%04d-%02d-%02dT%02d:%02d:00.000%s'/>\n",
                y, m, d, s[0], s[1], c->tzoffset, y, m, d, s[2], s[3], c->tzoffset);
        sb_adds(b, "    <gd:where valueString='Akihabara'/>\n");
        sb_adds(b, "    <gd:eventStatus value='http://schemas.google.com/g/2005#event.confirmed'/>\n");
        sb_adds(b, "  </entry>\n");
    }
    sb_adds(b, "</feed>\n");
}

static int count_events(const struct cfg *c) {
    char titles[64][256];
    return split_events(c->events, titles, 64);
}

/* ---- HTTP response assembly (shared by the :80 and :443 paths) ---------------- */
static void http_response(struct sb *out, int code, const char *reason,
                          const char *ctype, const char *body, int blen) {
    sb_addf(out, "HTTP/1.0 %d %s\r\n", code, reason);
    sb_addf(out, "Content-Type: %s\r\n", ctype);
    sb_addf(out, "Content-Length: %d\r\n", blen);
    sb_adds(out, "Connection: close\r\n\r\n");
    sb_add(out, body, blen);
}

/* Build the full response for one request. Returns the HTTP status code (for the log). */
static int http_handle(const struct cfg *c, const char *method, const char *path,
                       const char *query, const char *body, int bodylen,
                       char **resp, int *resplen) {
    (void)body; (void)bodylen;
    int code = 404;
    struct sb out; sb_init(&out);

    /* normalise: strip trailing slashes */
    char p[1024]; strncpy(p, path, sizeof(p) - 1); p[sizeof(p) - 1] = 0;
    int pl = (int)strlen(p); while (pl > 1 && p[pl - 1] == '/') p[--pl] = 0;

    if (!_stricmp(method, "POST") && !strcmp(p, "/accounts/ClientLogin")) {
        if (!strcmp(c->calendar, "error")) {
            const char *b = "Error=BadAuthentication\n";
            http_response(&out, 403, "Forbidden", "text/plain; charset=UTF-8", b, (int)strlen(b));
            code = 403;
        } else {
            const char *b = "SID=emu\nLSID=emu\nAuth=EMU_TEST_TOKEN\n";
            http_response(&out, 200, "OK", "text/plain; charset=UTF-8", b, (int)strlen(b));
            code = 200;
        }
    } else if (!_stricmp(method, "GET") && !strcmp(p, "/calendar/feeds/default/allcalendars/full")) {
        if (!strcmp(c->calendar, "error")) {
            const char *b = "Forbidden\n";
            http_response(&out, 403, "Forbidden", "text/plain", b, (int)strlen(b));
            code = 403;
        } else {
            struct sb body2; sb_init(&body2); build_allcalendars(&body2, c);
            http_response(&out, 200, "OK", "application/atom+xml; charset=UTF-8", body2.p, body2.len);
            free(body2.p); code = 200;
        }
    } else if (!_stricmp(method, "GET") && !strncmp(p, "/calendar/feeds/", 16)) {
        /* the event feed (any .../private/full the client built from our <link href=>) */
        if (!strcmp(c->calendar, "error")) {
            const char *b = "Forbidden\n";
            http_response(&out, 403, "Forbidden", "text/plain", b, (int)strlen(b));
            code = 403;
        } else {
            int n = (!strcmp(c->calendar, "none")) ? 0 : count_events(c);
            struct sb body2; sb_init(&body2);
            if (n) {
                build_events(&body2, c, query);
            } else {
                char cal[256]; xesc(c->calname, cal, sizeof(cal));
                sb_adds(&body2, "<?xml version='1.0' encoding='UTF-8'?>\n");
                sb_addf(&body2, "<feed %s>\n", ATOM_NS);
                sb_addf(&body2, "  <title type='text'>%s</title>\n</feed>\n", cal);
            }
            http_response(&out, 200, "OK", "application/atom+xml; charset=UTF-8", body2.p, body2.len);
            free(body2.p); code = 200;
        }
    } else if (!_stricmp(method, "GET") && !strcmp(p, "/calendar/event")) {
        const char *b = "<html><body>gcal-xp: add-event template (no-op stub)</body></html>";
        http_response(&out, 200, "OK", "text/html", b, (int)strlen(b));
        code = 200;
    } else {
        const char *b = "Not Found\n";
        http_response(&out, 404, "Not Found", "text/plain", b, (int)strlen(b));
        code = 404;
    }

    *resp = out.p; *resplen = out.len;
    return code;
}

/* ---- HTTP request parsing ----------------------------------------------------- */
/* case-insensitive find of header value; returns Content-Length or 0 */
static int header_content_length(const char *buf, int hdrlen) {
    const char *end = buf + hdrlen;
    for (const char *p = buf; p < end; p++) {
        if ((p == buf || p[-1] == '\n') && (end - p) > 15 && !_strnicmp(p, "Content-Length:", 15)) {
            p += 15; while (p < end && (*p == ' ' || *p == '\t')) p++;
            return atoi(p);
        }
    }
    return 0;
}
/* returns offset just past the blank line ending the headers, or -1 */
static int find_headers_end(const char *buf, int len) {
    for (int i = 0; i + 3 < len; i++)
        if (buf[i] == '\r' && buf[i + 1] == '\n' && buf[i + 2] == '\r' && buf[i + 3] == '\n')
            return i + 4;
    return -1;
}
/* is the buffer a complete request (headers + Content-Length body)? sets *total */
static int request_complete(const char *buf, int len, int *total) {
    int he = find_headers_end(buf, len);
    if (he < 0) return 0;
    int cl = header_content_length(buf, he);
    if (len >= he + cl) { *total = he + cl; return 1; }
    return 0;
}
/* split "METHOD URL HTTP/x" + url into path/query. Buffers caller-owned. */
static int parse_reqline(const char *buf, char *method, int mcap, char *path, int pcap,
                         char *query, int qcap, int *bodyoff, int *bodylen, int total) {
    const char *sp1 = strchr(buf, ' ');
    if (!sp1) return 0;
    const char *sp2 = strchr(sp1 + 1, ' ');
    if (!sp2) return 0;
    int ml = (int)(sp1 - buf); if (ml >= mcap) ml = mcap - 1;
    memcpy(method, buf, ml); method[ml] = 0;
    const char *url = sp1 + 1; int ul = (int)(sp2 - url);
    char urlbuf[1100]; if (ul >= (int)sizeof(urlbuf)) ul = sizeof(urlbuf) - 1;
    memcpy(urlbuf, url, ul); urlbuf[ul] = 0;
    char *q = strchr(urlbuf, '?');
    if (q) { *q = 0; strncpy(query, q + 1, qcap - 1); query[qcap - 1] = 0; }
    else query[0] = 0;
    strncpy(path, urlbuf, pcap - 1); path[pcap - 1] = 0;
    int he = find_headers_end(buf, total);
    *bodyoff = (he < 0) ? total : he;
    *bodylen = total - *bodyoff;
    return 1;
}

/* ---- socket helpers ----------------------------------------------------------- */
static int send_all(SOCKET s, const char *buf, int len) {
    int off = 0;
    while (off < len) { int n = send(s, buf + off, len - off, 0); if (n <= 0) return -1; off += n; }
    return 0;
}
static SOCKET listen_on(int port, const char *what) {
    SOCKET s = socket(AF_INET, SOCK_STREAM, 0);
    if (s == INVALID_SOCKET) { logln("%s: socket() failed %d", what, WSAGetLastError()); return INVALID_SOCKET; }
    int yes = 1; setsockopt(s, SOL_SOCKET, SO_REUSEADDR, (char *)&yes, sizeof(yes));
    struct sockaddr_in a; memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET; a.sin_addr.s_addr = INADDR_ANY; a.sin_port = htons((u_short)port);
    if (bind(s, (struct sockaddr *)&a, sizeof(a)) != 0) {
        logln("%s: bind(:%d) FAILED %d (port in use?)", what, port, WSAGetLastError());
        closesocket(s); return INVALID_SOCKET;
    }
    if (listen(s, 16) != 0) { logln("%s: listen() failed %d", what, WSAGetLastError()); closesocket(s); return INVALID_SOCKET; }
    logln("%s: listening on :%d", what, port);
    return s;
}
static void set_recv_timeout(SOCKET s) {
    DWORD t = RECV_TIMEOUT_MS; setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, (char *)&t, sizeof(t));
}
/* thread-safe peer IP into out (inet_ntoa uses a shared static buffer) */
static void peer_ip(SOCKET c, char *out, int cap) {
    struct sockaddr_in pa; int pl = sizeof(pa);
    strncpy(out, "?", cap); out[cap - 1] = 0;
    if (getpeername(c, (struct sockaddr *)&pa, &pl) == 0) {
        unsigned char *b = (unsigned char *)&pa.sin_addr;
        _snprintf(out, cap, "%u.%u.%u.%u", b[0], b[1], b[2], b[3]);
    }
}

/* ---- plain HTTP (:80) --------------------------------------------------------- */
static void serve_http_request(SOCKET c, const char *peer, const char *req, int total) {
    char method[16], path[1024], query[1100]; int bo, bl;
    if (!parse_reqline(req, method, sizeof(method), path, sizeof(path),
                       query, sizeof(query), &bo, &bl, total)) {
        logln("HTTP %s: bad request line", peer);
        const char *r = "HTTP/1.0 400 Bad Request\r\nContent-Length: 4\r\nConnection: close\r\n\r\nbad\n";
        send_all(c, r, (int)strlen(r));
        return;
    }
    logln("HTTP %s: %s %s%s%s", peer, method, path, query[0] ? "?" : "", query);
    struct cfg cf; cfg_load(&cf);
    char *resp; int rlen;
    int code = http_handle(&cf, method, path, query, req + bo, bl, &resp, &rlen);
    logln("HTTP %s: -> %d (%d bytes)", peer, code, rlen);
    send_all(c, resp, rlen);
    free(resp);
}

static DWORD WINAPI http_worker(void *arg) {
    SOCKET c = (SOCKET)(UINT_PTR)arg;
    char peer[32]; peer_ip(c, peer, sizeof(peer));
    set_recv_timeout(c);
    char *req = malloc(HTTP_REQ_CAP); int len = 0, total = 0;
    if (req) {
        for (;;) {
            int n = recv(c, req + len, HTTP_REQ_CAP - len - 1, 0);
            if (n <= 0) break;
            len += n; req[len] = 0;
            if (request_complete(req, len, &total)) { serve_http_request(c, peer, req, total); break; }
            if (len >= HTTP_REQ_CAP - 1) { logln("HTTP %s: request too large", peer); break; }
        }
        free(req);
    }
    closesocket(c);
    return 0;
}

static DWORD WINAPI http_listener(void *arg) {
    SOCKET s = (SOCKET)(UINT_PTR)arg;
    for (;;) {
        SOCKET c = accept(s, NULL, NULL);
        if (c == INVALID_SOCKET) continue;
        HANDLE h = CreateThread(NULL, 0, http_worker, (void *)(UINT_PTR)c, 0, NULL);
        if (h) CloseHandle(h); else closesocket(c);
    }
    return 0;
}

/* ---- POP3 (:110) -------------------------------------------------------------- */
static DWORD WINAPI pop3_worker(void *arg) {
    SOCKET c = (SOCKET)(UINT_PTR)arg;
    char peer[32]; peer_ip(c, peer, sizeof(peer));
    set_recv_timeout(c);

    struct cfg cf; cfg_load(&cf);
    if (!strcmp(cf.mail, "refuse")) { logln("POP3 %s: drop (mail=refuse)", peer); closesocket(c); return 0; }
    int n = (!strcmp(cf.mail, "check")) ? cf.mailcount : 0;
    if (n < 0) n = 0;
    int size = n * 1024;
    logln("POP3 %s: connect (mail=%s n=%d)", peer, cf.mail, n);

    #define POPSEND(s) do { send_all(c, (s), (int)strlen(s)); send_all(c, "\r\n", 2); logln("POP3 %s: -> %s", peer, s); } while (0)
    POPSEND("+OK gcal-xp POP3 ready");

    char line[1024]; int ll = 0;
    for (;;) {
        char ch; int r = recv(c, &ch, 1, 0);
        if (r <= 0) break;
        if (ch == '\n') {
            while (ll > 0 && (line[ll - 1] == '\r' || line[ll - 1] == ' ')) ll--;
            line[ll] = 0; ll = 0;
            char verb[16]; int i = 0;
            while (line[i] && line[i] != ' ' && i < 15) { verb[i] = (char)toupper((unsigned char)line[i]); i++; }
            verb[i] = 0;
            logln("POP3 %s: <- %s", peer, line);
            if      (!strcmp(verb, "USER")) POPSEND("+OK user accepted");
            else if (!strcmp(verb, "PASS")) { if (!strcmp(cf.mail, "error")) POPSEND("-ERR [AUTH] authentication failed"); else POPSEND("+OK mailbox ready"); }
            else if (!strcmp(verb, "STAT")) { char b[64]; _snprintf(b, sizeof(b), "+OK %d %d", n, size); POPSEND(b); }
            else if (!strcmp(verb, "LIST")) { char b[64]; _snprintf(b, sizeof(b), "+OK %d messages (%d octets)", n, size); POPSEND(b); for (int k = 1; k <= n; k++) { char l[32]; _snprintf(l, sizeof(l), "%d 1024", k); POPSEND(l); } POPSEND("."); }
            else if (!strcmp(verb, "UIDL")) { POPSEND("+OK"); for (int k = 1; k <= n; k++) { char l[32]; _snprintf(l, sizeof(l), "%d msg%04d", k, k); POPSEND(l); } POPSEND("."); }
            else if (!strcmp(verb, "CAPA")) POPSEND("-ERR no capabilities");
            else if (!strcmp(verb, "QUIT")) { POPSEND("+OK bye"); break; }
            else if (!strcmp(verb, "NOOP")) POPSEND("+OK");
            else POPSEND("-ERR unknown command");
        } else if (ll < (int)sizeof(line) - 1) {
            line[ll++] = ch;
        }
    }
    closesocket(c);
    return 0;
}

static DWORD WINAPI pop3_listener(void *arg) {
    SOCKET s = (SOCKET)(UINT_PTR)arg;
    for (;;) {
        SOCKET c = accept(s, NULL, NULL);
        if (c == INVALID_SOCKET) continue;
        HANDLE h = CreateThread(NULL, 0, pop3_worker, (void *)(UINT_PTR)c, 0, NULL);
        if (h) CloseHandle(h); else closesocket(c);
    }
    return 0;
}

/* ---- Schannel HTTPS (:443) ---------------------------------------------------- */

/* Acquire the server credential from the embedded PFX; install the cert into Root. */
static int tls_init(void) {
    CRYPT_DATA_BLOB pfx; pfx.cbData = CERT_PFX_LEN; pfx.pbData = (BYTE *)CERT_PFX;
    /* The user keyset works in an interactive user session; a SYSTEM/service context
     * (e.g. launched via SMB exec) needs the MACHINE keyset, else the import fails
     * with NTE_BAD_KEYSET (0x8009000b). Try user first, fall back to machine. */
    HCERTSTORE hPfx = PFXImportCertStore(&pfx, CERT_PFX_PASS, CRYPT_EXPORTABLE);
    if (!hPfx) {
        logln("TLS: PFX user-keyset import failed 0x%08lx; retrying machine keyset", GetLastError());
        hPfx = PFXImportCertStore(&pfx, CERT_PFX_PASS, CRYPT_EXPORTABLE | CRYPT_MACHINE_KEYSET);
    }
    if (!hPfx) { logln("TLS: PFXImportCertStore failed 0x%08lx", GetLastError()); return 0; }
    g_pCert = CertFindCertificateInStore(hPfx, X509_ASN_ENCODING | PKCS_7_ASN_ENCODING,
                                         0, CERT_FIND_ANY, NULL, NULL);
    if (!g_pCert) { logln("TLS: no cert in PFX store 0x%08lx", GetLastError()); CertCloseStore(hPfx, 0); return 0; }

    SCHANNEL_CRED sc; memset(&sc, 0, sizeof(sc));
    sc.dwVersion = SCHANNEL_CRED_VERSION;
    sc.cCreds = 1;
    sc.paCred = &g_pCert;
    sc.grbitEnabledProtocols = SP_PROT_TLS1_SERVER | SP_PROT_SSL3_SERVER;  /* XP SP3 era */
    TimeStamp ts;
    SECURITY_STATUS ss = AcquireCredentialsHandleA(NULL, (SEC_CHAR *)UNISP_NAME_A,
            SECPKG_CRED_INBOUND, NULL, &sc, NULL, NULL, &g_hCred, &ts);
    if (ss != SEC_E_OK) { logln("TLS: AcquireCredentialsHandle failed 0x%08lx", (unsigned long)ss); return 0; }
    logln("TLS: server credential acquired (cert CN=www.google.com)");
    return 1;
}

/* Install the public cert into XP's Root so WinINet trusts the TLS endpoint.
 * Runs in a BACKGROUND thread: on XP, CertAddEncodedCertificateToStore to a Root
 * store pops a protected-root confirmation MODAL, which would block startup before
 * the listeners bind. Threading it off lets the server serve regardless. (If gcal.exe
 * ignores cert errors the prompt is moot; for a silent unattended install, import the
 * cert via certutil/registry instead — see the README.) */
static DWORD WINAPI cert_install_thread(void *arg) {
    (void)arg;
    if (!g_pCert) return 0;
    HCERTSTORE hRootU = CertOpenStore(CERT_STORE_PROV_SYSTEM_A, 0, 0, CERT_SYSTEM_STORE_CURRENT_USER, "ROOT");
    if (hRootU) {
        BOOL ok = CertAddEncodedCertificateToStore(hRootU, X509_ASN_ENCODING,
                    g_pCert->pbCertEncoded, g_pCert->cbCertEncoded, CERT_STORE_ADD_REPLACE_EXISTING, NULL);
        logln("cert: install -> CurrentUser\\Root: %s", ok ? "ok" : "FAILED");
        CertCloseStore(hRootU, 0);
    } else logln("cert: open CurrentUser\\Root failed 0x%08lx", GetLastError());
    HCERTSTORE hRootM = CertOpenStore(CERT_STORE_PROV_SYSTEM_A, 0, 0, CERT_SYSTEM_STORE_LOCAL_MACHINE, "ROOT");
    if (hRootM) {
        BOOL ok = CertAddEncodedCertificateToStore(hRootM, X509_ASN_ENCODING,
                    g_pCert->pbCertEncoded, g_pCert->cbCertEncoded, CERT_STORE_ADD_REPLACE_EXISTING, NULL);
        logln("cert: install -> LocalMachine\\Root: %s", ok ? "ok" : "FAILED(no admin?)");
        CertCloseStore(hRootM, 0);
    }
    return 0;
}

/* Server-side handshake. On success: *ctx valid, inbuf[0..*inlen) holds leftover app bytes. */
static int tls_handshake(SOCKET c, const char *peer, CtxtHandle *ctx, char *inbuf, int *inlen) {
    BOOL haveCtx = FALSE;
    *inlen = 0;
    for (;;) {
        if (*inlen == 0) {
            int n = recv(c, inbuf + *inlen, TLS_INBUF_CAP - *inlen, 0);
            if (n <= 0) { logln("TLS %s: recv during handshake -> %d", peer, n); if (haveCtx) DeleteSecurityContext(ctx); return 0; }
            *inlen += n;
        }
        SecBuffer inb[2];
        inb[0].pvBuffer = inbuf; inb[0].cbBuffer = *inlen; inb[0].BufferType = SECBUFFER_TOKEN;
        inb[1].pvBuffer = NULL;  inb[1].cbBuffer = 0;      inb[1].BufferType = SECBUFFER_EMPTY;
        SecBufferDesc ind = { SECBUFFER_VERSION, 2, inb };
        SecBuffer outb[1];
        outb[0].pvBuffer = NULL; outb[0].cbBuffer = 0; outb[0].BufferType = SECBUFFER_TOKEN;
        SecBufferDesc outd = { SECBUFFER_VERSION, 1, outb };
        DWORD attr = 0; TimeStamp ts;
        SECURITY_STATUS ss = AcceptSecurityContext(&g_hCred, haveCtx ? ctx : NULL, &ind,
                ASC_REQ_SEQUENCE_DETECT | ASC_REQ_REPLAY_DETECT | ASC_REQ_CONFIDENTIALITY |
                ASC_REQ_EXTENDED_ERROR | ASC_REQ_ALLOCATE_MEMORY | ASC_REQ_STREAM,
                0, ctx, &outd, &attr, &ts);

        if (ss == SEC_E_INCOMPLETE_MESSAGE) {
            int n = recv(c, inbuf + *inlen, TLS_INBUF_CAP - *inlen, 0);
            if (n <= 0) { logln("TLS %s: recv (incomplete) -> %d", peer, n); if (haveCtx) DeleteSecurityContext(ctx); return 0; }
            *inlen += n;
            continue;
        }
        /* A context exists (and `ctx` is valid) ONLY if ASC succeeded or wants another
         * round. On a first-call hard failure no context is created — deleting `ctx`
         * then is an access violation. */
        if (ss == SEC_E_OK || ss == SEC_I_CONTINUE_NEEDED) haveCtx = TRUE;

        if (outb[0].cbBuffer && outb[0].pvBuffer) {
            send_all(c, (char *)outb[0].pvBuffer, outb[0].cbBuffer);
            FreeContextBuffer(outb[0].pvBuffer);
        }

        int extra = (inb[1].BufferType == SECBUFFER_EXTRA) ? (int)inb[1].cbBuffer : 0;
        if (extra) { memmove(inbuf, inbuf + (*inlen - extra), extra); *inlen = extra; }
        else *inlen = 0;

        if (ss == SEC_E_OK) { logln("TLS %s: handshake complete", peer); return 1; }
        if (ss == SEC_I_CONTINUE_NEEDED) continue;
        logln("TLS %s: AcceptSecurityContext failed 0x%08lx", peer, (unsigned long)ss);
        if (haveCtx) DeleteSecurityContext(ctx);
        return 0;
    }
}

/* Read + decrypt one full HTTP request over the established context. */
static int tls_read_request(SOCKET c, const char *peer, CtxtHandle *ctx,
                            char *inbuf, int *inlen, char *req, int reqcap, int *total) {
    int reqlen = 0;
    for (;;) {
        if (*inlen == 0) {
            int n = recv(c, inbuf + *inlen, TLS_INBUF_CAP - *inlen, 0);
            if (n <= 0) { logln("TLS %s: recv (read) -> %d", peer, n); return 0; }
            *inlen += n;
        }
        SecBuffer b[4];
        b[0].pvBuffer = inbuf; b[0].cbBuffer = *inlen; b[0].BufferType = SECBUFFER_DATA;
        b[1].BufferType = SECBUFFER_EMPTY; b[2].BufferType = SECBUFFER_EMPTY; b[3].BufferType = SECBUFFER_EMPTY;
        SecBufferDesc d = { SECBUFFER_VERSION, 4, b };
        SECURITY_STATUS ss = DecryptMessage(ctx, &d, 0, NULL);
        if (ss == SEC_E_INCOMPLETE_MESSAGE) {
            int n = recv(c, inbuf + *inlen, TLS_INBUF_CAP - *inlen, 0);
            if (n <= 0) { logln("TLS %s: recv (decrypt-incomplete) -> %d", peer, n); return 0; }
            *inlen += n;
            continue;
        }
        if (ss != SEC_E_OK && ss != SEC_I_RENEGOTIATE && ss != SEC_I_CONTEXT_EXPIRED) {
            logln("TLS %s: DecryptMessage failed 0x%08lx", peer, (unsigned long)ss);
            return 0;
        }
        SecBuffer *data = NULL, *xtra = NULL;
        for (int i = 0; i < 4; i++) {
            if (b[i].BufferType == SECBUFFER_DATA && !data) data = &b[i];
            if (b[i].BufferType == SECBUFFER_EXTRA && !xtra) xtra = &b[i];
        }
        if (data && data->cbBuffer) {
            int cp = (int)data->cbBuffer; if (reqlen + cp > reqcap - 1) cp = reqcap - 1 - reqlen;
            if (cp > 0) { memcpy(req + reqlen, data->pvBuffer, cp); reqlen += cp; req[reqlen] = 0; }
        }
        if (xtra && xtra->cbBuffer) { memmove(inbuf, xtra->pvBuffer, xtra->cbBuffer); *inlen = (int)xtra->cbBuffer; }
        else *inlen = 0;

        if (request_complete(req, reqlen, total)) return 1;
        if (reqlen >= reqcap - 1) { logln("TLS %s: request too large", peer); return 0; }
        if (ss == SEC_I_CONTEXT_EXPIRED) { logln("TLS %s: peer closed mid-request", peer); return 0; }
    }
}

/* Encrypt + send a full plaintext response, chunked to the stream max message size. */
static int tls_send(SOCKET c, CtxtHandle *ctx, SecPkgContext_StreamSizes *sz, const char *plain, int len) {
    int off = 0;
    char *buf = malloc(sz->cbHeader + sz->cbMaximumMessage + sz->cbTrailer);
    if (!buf) return -1;
    while (off < len) {
        int chunk = len - off; if (chunk > (int)sz->cbMaximumMessage) chunk = (int)sz->cbMaximumMessage;
        memcpy(buf + sz->cbHeader, plain + off, chunk);
        SecBuffer b[4];
        b[0].pvBuffer = buf;                         b[0].cbBuffer = sz->cbHeader;  b[0].BufferType = SECBUFFER_STREAM_HEADER;
        b[1].pvBuffer = buf + sz->cbHeader;          b[1].cbBuffer = chunk;         b[1].BufferType = SECBUFFER_DATA;
        b[2].pvBuffer = buf + sz->cbHeader + chunk;  b[2].cbBuffer = sz->cbTrailer; b[2].BufferType = SECBUFFER_STREAM_TRAILER;
        b[3].pvBuffer = NULL; b[3].cbBuffer = 0; b[3].BufferType = SECBUFFER_EMPTY;
        SecBufferDesc d = { SECBUFFER_VERSION, 4, b };
        SECURITY_STATUS ss = EncryptMessage(ctx, 0, &d, 0);
        if (ss != SEC_E_OK) { logln("TLS: EncryptMessage failed 0x%08lx", (unsigned long)ss); free(buf); return -1; }
        int tot = (int)(b[0].cbBuffer + b[1].cbBuffer + b[2].cbBuffer);
        if (send_all(c, buf, tot) != 0) { free(buf); return -1; }
        off += chunk;
    }
    free(buf);
    return 0;
}

static DWORD WINAPI https_worker(void *arg) {
    SOCKET c = (SOCKET)(UINT_PTR)arg;
    char peer[32]; peer_ip(c, peer, sizeof(peer));
    set_recv_timeout(c);
    logln("TLS %s: connection", peer);

    char *inbuf = malloc(TLS_INBUF_CAP);
    char *req = malloc(HTTP_REQ_CAP);
    CtxtHandle ctx; int inlen = 0, total = 0;
    if (inbuf && req && tls_handshake(c, peer, &ctx, inbuf, &inlen)) {
        SecPkgContext_StreamSizes sz;
        if (QueryContextAttributes(&ctx, SECPKG_ATTR_STREAM_SIZES, &sz) == SEC_E_OK) {
            if (tls_read_request(c, peer, &ctx, inbuf, &inlen, req, HTTP_REQ_CAP, &total)) {
                char method[16], path[1024], query[1100]; int bo, bl;
                if (parse_reqline(req, method, sizeof(method), path, sizeof(path),
                                  query, sizeof(query), &bo, &bl, total)) {
                    logln("TLS %s: %s %s%s%s", peer, method, path, query[0] ? "?" : "", query);
                    struct cfg cf; cfg_load(&cf);
                    char *resp; int rlen;
                    int code = http_handle(&cf, method, path, query, req + bo, bl, &resp, &rlen);
                    logln("TLS %s: -> %d (%d bytes)", peer, code, rlen);
                    tls_send(c, &ctx, &sz, resp, rlen);
                    free(resp);
                }
            }
        } else logln("TLS %s: QueryContextAttributes(STREAM_SIZES) failed", peer);
        DeleteSecurityContext(&ctx);
    }
    free(inbuf); free(req);
    closesocket(c);
    return 0;
}

static DWORD WINAPI https_listener(void *arg) {
    SOCKET s = (SOCKET)(UINT_PTR)arg;
    for (;;) {
        SOCKET c = accept(s, NULL, NULL);
        if (c == INVALID_SOCKET) continue;
        HANDLE h = CreateThread(NULL, 0, https_worker, (void *)(UINT_PTR)c, 0, NULL);
        if (h) CloseHandle(h); else closesocket(c);
    }
    return 0;
}

/* ---- first-run install (hosts redirect + autostart) --------------------------- */
static void do_install(void) {
    /* 1) hosts: www.google.com -> 127.0.0.1 (append once) */
    char hosts[MAX_PATH]; GetWindowsDirectoryA(hosts, sizeof(hosts));
    strcat(hosts, "\\system32\\drivers\\etc\\hosts");
    int present = 0;
    FILE *f = fopen(hosts, "r");
    if (f) { char ln[512]; while (fgets(ln, sizeof(ln), f)) if (strstr(ln, "www.google.com")) { present = 1; break; } fclose(f); }
    if (!present) {
        f = fopen(hosts, "a");
        if (f) { fputs("\r\n127.0.0.1\twww.google.com\r\n", f); fclose(f); logln("install: hosts redirect added"); }
        else logln("install: could not write hosts (admin?)");
    } else logln("install: hosts already has a www.google.com line");

    /* 2) autostart: copy self into the All Users Startup folder */
    char self[MAX_PATH]; GetModuleFileNameA(NULL, self, sizeof(self));
    char startup[MAX_PATH];
    if (GetEnvironmentVariableA("ALLUSERSPROFILE", startup, sizeof(startup)) > 0) {
        strcat(startup, "\\Start Menu\\Programs\\Startup\\gcalsrv.exe");
        if (CopyFileA(self, startup, FALSE)) logln("install: copied to Startup (%s)", startup);
        else logln("install: Startup copy failed 0x%08lx", GetLastError());
    }
}

/* ---- main --------------------------------------------------------------------- */
int main(int argc, char **argv) {
    int want_install = 0, want_tls = 1, want_cert = 1;
    for (int i = 1; i < argc; i++) {
        if      (!strcmp(argv[i], "--install"))    want_install = 1;
        else if (!strcmp(argv[i], "--no-tls"))     want_tls = 0;
        else if (!strcmp(argv[i], "--no-cert"))    want_cert = 0;
        else if (!strcmp(argv[i], "--http")  && i + 1 < argc) g_http_port  = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--https") && i + 1 < argc) g_https_port = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--pop")   && i + 1 < argc) g_pop_port   = atoi(argv[++i]);
    }

    /* Never pop a Windows Error Reporting / crash modal — a server fault must not
     * block the (often headless) XP box. A faulting worker thread just dies; the
     * listeners keep running. */
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX);

    GetModuleFileNameA(NULL, g_exedir, sizeof(g_exedir));
    char *sl = strrchr(g_exedir, '\\'); if (sl) *sl = 0;
    _snprintf(g_logpath, sizeof(g_logpath), "%s\\gcalsrv.log", g_exedir);
    _snprintf(g_inipath, sizeof(g_inipath), "%s\\gcal-xp.ini", g_exedir);
    InitializeCriticalSection(&g_loglock);

    logln("==================================================================");
    logln("gcalsrv starting (http=:%d https=:%d pop=:%d) dir=%s",
         g_http_port, g_https_port, g_pop_port, g_exedir);
    logln("config: %s   log: %s", g_inipath, g_logpath);

    WSADATA w;
    if (WSAStartup(MAKEWORD(2, 2), &w) != 0) { logln("FATAL: WSAStartup failed"); return 1; }

    if (want_install) do_install();

    if (want_tls) g_tls_ok = tls_init();

    SOCKET sh = listen_on(g_http_port, "HTTP");
    SOCKET ss = (want_tls && g_tls_ok) ? listen_on(g_https_port, "HTTPS") : INVALID_SOCKET;
    SOCKET sp = listen_on(g_pop_port, "POP3");

    HANDLE threads[3]; int nt = 0;
    if (sh != INVALID_SOCKET) threads[nt++] = CreateThread(NULL, 0, http_listener,  (void *)(UINT_PTR)sh, 0, NULL);
    if (ss != INVALID_SOCKET) threads[nt++] = CreateThread(NULL, 0, https_listener, (void *)(UINT_PTR)ss, 0, NULL);
    if (sp != INVALID_SOCKET) threads[nt++] = CreateThread(NULL, 0, pop3_listener,  (void *)(UINT_PTR)sp, 0, NULL);

    if (nt == 0) { logln("FATAL: no listeners came up"); return 1; }
    /* Install the cert AFTER the listeners are up, in a detached thread, so the XP
     * protected-root modal (if any) can never block serving. */
    if (g_tls_ok && want_cert) {
        HANDLE ct = CreateThread(NULL, 0, cert_install_thread, NULL, 0, NULL);
        if (ct) CloseHandle(ct);
    }
    logln("gcalsrv ready (%d listener%s)", nt, nt == 1 ? "" : "s");
    WaitForMultipleObjects(nt, threads, TRUE, INFINITE);
    return 0;
}
