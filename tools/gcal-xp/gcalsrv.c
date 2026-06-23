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
#include <shellapi.h>
#include <wincrypt.h>
#include <schannel.h>
#include <security.h>
#include <sspi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <ctype.h>

#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"

/* embedded www.google.com PKCS#12 (CERT_PFX / CERT_PFX_LEN / CERT_PFX_PASS) */
#include "cert_pfx.h"
/* embedded default request-logic script (GCALSRV_LUA / GCALSRV_LUA_LEN) */
#include "gcalsrv_lua.h"

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
static int   g_tray       = 1;          /* show the tray UI (interactive); --no-tray for headless */
static int   g_tls_ok     = 0;          /* set once Schannel creds are acquired */
static char  g_exedir[MAX_PATH];
static char  g_logpath[MAX_PATH];
static char  g_inipath[MAX_PATH];
static CRITICAL_SECTION g_loglock;

static CredHandle    g_hCred;           /* Schannel server credential (shared, read-only) */
static PCCERT_CONTEXT g_pCert = NULL;   /* our www.google.com cert (with private key) */

static lua_State    *g_L = NULL;        /* request logic (gcalsrv.lua) */
static CRITICAL_SECTION g_lua_lock;     /* one shared lua_State, serialised (low volume) */

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

/* ---- Lua bridge: the request logic lives in gcalsrv.lua ----------------------- */
static const char *http_reason(int code) {
    switch (code) {
        case 200: return "OK";
        case 400: return "Bad Request";
        case 403: return "Forbidden";
        case 404: return "Not Found";
        case 500: return "Internal Server Error";
        default:  return "OK";
    }
}

/* C functions exposed to the script */
static int l_log(lua_State *L)    { logln("lua: %s", luaL_optstring(L, 1, "")); return 0; }
static int l_exedir(lua_State *L) { lua_pushstring(L, g_exedir); return 1; }

/* Register the C API + load gcalsrv.lua (external <exedir> copy if present, else the embedded
 * default) into L, run it, and verify the handlers are defined. On any failure write a human
 * message into err[] and return 0 — the caller decides whether to pop an error dialog. */
static int lua_load_into(lua_State *L, char *err, int errsz) {
    luaL_openlibs(L);
    lua_register(L, "gcalsrv_log", l_log);
    lua_register(L, "gcalsrv_exedir", l_exedir);
    char path[MAX_PATH];
    _snprintf(path, sizeof(path), "%s\\gcalsrv.lua", g_exedir);
    int ext = (luaL_loadfile(L, path) == LUA_OK);
    if (!ext) {
        lua_pop(L, 1);   /* drop the loadfile error; fall back to the embedded default */
        if (luaL_loadbuffer(L, (const char *)GCALSRV_LUA, GCALSRV_LUA_LEN, "gcalsrv.lua") != LUA_OK) {
            _snprintf(err, errsz, "Couldn't load the script:\n\n%s", lua_tostring(L, -1));
            return 0;
        }
    }
    if (lua_pcall(L, 0, 0, 0) != LUA_OK) {
        _snprintf(err, errsz, "Error in gcalsrv.lua:\n\n%s", lua_tostring(L, -1));
        return 0;
    }
    lua_getglobal(L, "http_handle");
    int ok = lua_isfunction(L, -1);
    lua_pop(L, 1);
    if (!ok) { _snprintf(err, errsz, "gcalsrv.lua: http_handle() is not defined."); return 0; }
    logln("LUA: loaded %s", ext ? path : "embedded script");
    return 1;
}

static int lua_init(void) {
    g_L = luaL_newstate();
    if (!g_L) { logln("LUA: newstate failed"); return 0; }
    InitializeCriticalSection(&g_lua_lock);
    char err[600];
    if (!lua_load_into(g_L, err, sizeof(err))) {
        logln("LUA: %s", err);
        if (g_tray) MessageBoxA(NULL, err, "gcal-xp - Lua error", MB_OK | MB_ICONERROR | MB_SETFOREGROUND);
        return 0;
    }
    logln("LUA: ready");
    return 1;
}

/* Hot-reload after the user edits gcalsrv.lua: load it into a FRESH state, and only if that
 * succeeds swap it in under the lock; on error keep serving with the previous script and show
 * the Lua message. (Driven by watch_thread -> WM_APP_RELOAD on the UI thread.) */
static void lua_reload(void) {
    lua_State *nL = luaL_newstate();
    if (!nL) return;
    char err[600];
    if (!lua_load_into(nL, err, sizeof(err))) {
        logln("LUA reload: %s", err);
        if (g_tray) MessageBoxA(NULL, err, "gcal-xp - Lua error (kept the previous script)",
                                MB_OK | MB_ICONWARNING | MB_SETFOREGROUND);
        lua_close(nL);
        return;
    }
    EnterCriticalSection(&g_lua_lock);
    lua_State *old = g_L; g_L = nL;
    LeaveCriticalSection(&g_lua_lock);
    lua_close(old);
    logln("LUA: hot-reloaded gcalsrv.lua");
}

/* XML-escape, the Atom builders, event splitting, scenario/config loading, and the
 * HTTP routing all moved to gcalsrv.lua. The C side keeps only transport + framing. */

/* Call http_handle(method,path,query,body) -> status,ctype,body; frame the full
 * HTTP/1.0 response (status line + headers + body) into *resp. Returns the status. */
static int lua_http(const char *method, const char *path, const char *query,
                    const char *body, int bodylen, char **resp, int *resplen) {
    int status = 500;
    char ctype[128]; strcpy(ctype, "text/plain");
    char *bodyout = NULL; int blen = 0;

    EnterCriticalSection(&g_lua_lock);
    lua_settop(g_L, 0);
    lua_getglobal(g_L, "http_handle");
    lua_pushstring(g_L, method);
    lua_pushstring(g_L, path);
    lua_pushstring(g_L, query ? query : "");
    lua_pushlstring(g_L, body ? body : "", (size_t)bodylen);
    if (lua_pcall(g_L, 4, 3, 0) != LUA_OK) {
        logln("LUA: http_handle error: %s", lua_tostring(g_L, -1));
    } else {
        status = (int)luaL_optinteger(g_L, 1, 200);
        strncpy(ctype, luaL_optstring(g_L, 2, "text/plain"), sizeof(ctype) - 1);
        ctype[sizeof(ctype) - 1] = 0;
        size_t n = 0;
        const char *b = lua_tolstring(g_L, 3, &n);   /* copy the body out before we unlock */
        blen = (int)n;
        bodyout = malloc(blen + 1);
        if (bodyout) { if (b) memcpy(bodyout, b, blen); bodyout[blen] = 0; } else blen = 0;
    }
    lua_settop(g_L, 0);
    LeaveCriticalSection(&g_lua_lock);

    struct sb out; sb_init(&out);
    sb_addf(&out, "HTTP/1.0 %d %s\r\n", status, http_reason(status));
    sb_addf(&out, "Content-Type: %s\r\n", ctype);
    sb_addf(&out, "Content-Length: %d\r\n", blen);
    sb_adds(&out, "Connection: close\r\n\r\n");
    if (bodyout) sb_add(&out, bodyout, blen);
    free(bodyout);
    *resp = out.p; *resplen = out.len;
    return status;
}

/* POP3 action codes returned by lua_pop3() */
enum { POP_SEND = 0, POP_QUIT = 1, POP_DROP = 2 };

/* Call pop3_event(verb,arg) -> reply,action. *reply is malloc'd (caller frees) or NULL.
 * reply may be multi-line (\r\n-joined); the worker appends the trailing CRLF. */
static int lua_pop3(const char *verb, const char *arg, char **reply, int *replylen) {
    int action = POP_SEND;
    *reply = NULL; *replylen = 0;
    EnterCriticalSection(&g_lua_lock);
    lua_settop(g_L, 0);
    lua_getglobal(g_L, "pop3_event");
    if (lua_isfunction(g_L, -1)) {
        lua_pushstring(g_L, verb);
        lua_pushstring(g_L, arg ? arg : "");
        if (lua_pcall(g_L, 2, 2, 0) != LUA_OK) {
            logln("LUA: pop3_event error: %s", lua_tostring(g_L, -1));
        } else {
            size_t n = 0;
            const char *r = lua_tolstring(g_L, 1, &n);   /* nil => no reply (drop) */
            const char *act = luaL_optstring(g_L, 2, "send");
            if (r) { *reply = malloc(n + 1); if (*reply) { memcpy(*reply, r, n); (*reply)[n] = 0; *replylen = (int)n; } }
            if (!strcmp(act, "quit")) action = POP_QUIT;
            else if (!strcmp(act, "drop")) action = POP_DROP;
        }
    }
    lua_settop(g_L, 0);
    LeaveCriticalSection(&g_lua_lock);
    return action;
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
    char *resp; int rlen;
    int code = lua_http(method, path, query, req + bo, bl, &resp, &rlen);
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

    /* greeting / refuse decision via Lua (verb "CONNECT") */
    char *reply; int rlen;
    int act = lua_pop3("CONNECT", "", &reply, &rlen);
    if (act == POP_DROP) { logln("POP3 %s: drop (scenario)", peer); free(reply); closesocket(c); return 0; }
    logln("POP3 %s: connect", peer);
    if (reply) { send_all(c, reply, rlen); send_all(c, "\r\n", 2); logln("POP3 %s: -> %s", peer, reply); free(reply); }

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
            const char *sp = strchr(line, ' ');
            logln("POP3 %s: <- %s", peer, line);
            act = lua_pop3(verb, sp ? sp + 1 : "", &reply, &rlen);
            if (reply) { send_all(c, reply, rlen); send_all(c, "\r\n", 2); logln("POP3 %s: -> %s", peer, reply); free(reply); }
            if (act == POP_QUIT || act == POP_DROP) break;
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
    char cn[128] = "?";
    CertGetNameStringA(g_pCert, CERT_NAME_SIMPLE_DISPLAY_TYPE, 0, NULL, cn, sizeof(cn));
    logln("TLS: server credential acquired (cert CN=%s)", cn);   /* read it; don't hardcode */
    return 1;
}

/* Trust the embedded cert by writing it to HKLM\SOFTWARE\Microsoft\SystemCertificates\Root
 * through the REGISTRY store provider — the SILENT path. The SYSTEM store provider
 * (CERT_STORE_PROV_SYSTEM + CERT_SYSTEM_STORE_LOCAL_MACHINE "ROOT") pops XP's protected-root
 * confirmation MODAL(s) on an interactive Root add — and CERT_STORE_ADD_REPLACE_EXISTING makes
 * it TWO prompts ("delete this root cert?" then "install this root cert?"). The installer runs
 * --install-cert as the logged-in (elevated) user, so the user saw both. The raw registry
 * provider is plain registry I/O: no UI, and WinINet/Schannel still trust it because HKLM
 * ...\SystemCertificates\Root IS the machine root store. Requires admin (the installer is
 * elevated); CertCloseStore flushes the serialized cert blob to the registry. */
static int install_root_cert_silent(void) {
    if (!g_pCert) return 0;
    HKEY hk;
    LONG rc = RegCreateKeyExA(HKEY_LOCAL_MACHINE,
        "SOFTWARE\\Microsoft\\SystemCertificates\\Root", 0, NULL,
        REG_OPTION_NON_VOLATILE, KEY_READ | KEY_WRITE, NULL, &hk, NULL);
    if (rc != ERROR_SUCCESS) { logln("cert: open HKLM Root key failed (%ld) — admin?", rc); return 0; }
    HCERTSTORE h = CertOpenStore(CERT_STORE_PROV_REG, X509_ASN_ENCODING, 0, 0, (const void *)hk);
    if (!h) { logln("cert: CertOpenStore(REG Root) failed 0x%08lx", GetLastError()); RegCloseKey(hk); return 0; }
    BOOL ok = CertAddEncodedCertificateToStore(h, X509_ASN_ENCODING, g_pCert->pbCertEncoded,
                g_pCert->cbCertEncoded, CERT_STORE_ADD_REPLACE_EXISTING, NULL);
    CertCloseStore(h, 0);                       /* flush the new cert blob to the registry */
    RegCloseKey(hk);
    logln("cert: install -> HKLM\\...\\Root (registry, silent): %s", ok ? "ok" : "FAILED");
    return ok;
}

/* Background thread so a (now-silent) cert install can never block serving. */
static DWORD WINAPI cert_install_thread(void *arg) {
    (void)arg;
    install_root_cert_silent();
    return 0;
}

/* --install-cert: silently trust the embedded cert (elevated installer step), then exit, so the
 * autostarted gcalsrv can run --no-cert. */
static int cert_install_machine(void) {
    return install_root_cert_silent();
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
                    char *resp; int rlen;
                    int code = lua_http(method, path, query, req + bo, bl, &resp, &rlen);
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
/* ---- system-tray UI (interactive session; skipped under --no-tray) ------------- */
#define WM_TRAY        (WM_APP + 1)
#define WM_APP_RELOAD  (WM_APP + 2)
#define IDM_OPENLUA    1
#define IDM_ABOUT      2
#define IDM_EXIT       3

static HWND            g_tray_wnd = NULL;
static NOTIFYICONDATAA g_nid;

static const char *ABOUT_TEXT =
    "gcal-xp - fake Google server for Lucky*Mas\r\n"
    "\r\n"
    "Runs on your PC so the desktop mascots' calendar and mail work with no\r\n"
    "Google account: it answers as www.google.com over Windows' own 2007 TLS\r\n"
    "stack, serving calendar events + POP3 mail - all locally.\r\n"
    "\r\n"
    "Set your own events/mail by editing gcalsrv.lua (tray menu -> Open\r\n"
    "gcalsrv.lua); it hot-reloads when you save.\r\n"
    "\r\n"
    "Part of the LuckyMasEN English patch:\r\n"
    "https://github.com/Francesco149/LuckyMasEN";

/* Open gcalsrv.lua in the default editor; if there's no external copy yet, drop the embedded
 * default first so the user has something to edit. */
static void open_lua(HWND h) {
    char path[MAX_PATH];
    _snprintf(path, sizeof(path), "%s\\gcalsrv.lua", g_exedir);
    if (GetFileAttributesA(path) == INVALID_FILE_ATTRIBUTES) {
        FILE *f = fopen(path, "wb");
        if (f) { fwrite(GCALSRV_LUA, 1, GCALSRV_LUA_LEN, f); fclose(f); logln("wrote default gcalsrv.lua for editing"); }
    }
    /* .lua has no XP file association, so ShellExecute "open" does nothing -> open in Notepad
     * explicitly (quote the path; it contains spaces under Program Files). */
    {
        char param[MAX_PATH + 4];
        _snprintf(param, sizeof(param), "\"%s\"", path);
        ShellExecuteA(h, NULL, "notepad.exe", param, NULL, SW_SHOWNORMAL);
    }
}

static LRESULT CALLBACK tray_proc(HWND h, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_TRAY:
        if (lp == WM_RBUTTONUP || lp == WM_LBUTTONUP) {
            POINT pt; GetCursorPos(&pt);
            HMENU m = CreatePopupMenu();
            AppendMenuA(m, MF_STRING, IDM_OPENLUA, "Open gcalsrv.lua");
            AppendMenuA(m, MF_STRING, IDM_ABOUT,   "About gcal-xp...");
            AppendMenuA(m, MF_SEPARATOR, 0, NULL);
            AppendMenuA(m, MF_STRING, IDM_EXIT,    "Close");
            SetForegroundWindow(h);                       /* so the menu closes on click-away */
            TrackPopupMenu(m, TPM_RIGHTBUTTON | TPM_BOTTOMALIGN, pt.x, pt.y, 0, h, NULL);
            DestroyMenu(m);
        }
        return 0;
    case WM_COMMAND:
        switch (LOWORD(wp)) {
        case IDM_OPENLUA: open_lua(h); break;
        case IDM_ABOUT:   MessageBoxA(h, ABOUT_TEXT, "About gcal-xp", MB_OK | MB_ICONINFORMATION); break;
        case IDM_EXIT:    Shell_NotifyIconA(NIM_DELETE, &g_nid); PostQuitMessage(0); break;
        }
        return 0;
    case WM_APP_RELOAD:
        lua_reload();
        return 0;
    case WM_DESTROY:
        Shell_NotifyIconA(NIM_DELETE, &g_nid);
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcA(h, msg, wp, lp);
}

/* Poll gcalsrv.lua's mtime (cheap, and unlike a directory change-notification it ignores the
 * constant gcalsrv.log writes) and ask the UI thread to hot-reload when it changes. */
static DWORD WINAPI watch_thread(void *arg) {
    char path[MAX_PATH];
    _snprintf(path, sizeof(path), "%s\\gcalsrv.lua", g_exedir);
    FILETIME last = {0, 0};
    WIN32_FILE_ATTRIBUTE_DATA fad;
    if (GetFileAttributesExA(path, GetFileExInfoStandard, &fad)) last = fad.ftLastWriteTime;
    for (;;) {
        Sleep(1000);
        if (GetFileAttributesExA(path, GetFileExInfoStandard, &fad) &&
            CompareFileTime(&fad.ftLastWriteTime, &last) != 0) {
            last = fad.ftLastWriteTime;
            Sleep(250);                                   /* let the editor finish writing */
            if (g_tray_wnd) PostMessageA(g_tray_wnd, WM_APP_RELOAD, 0, 0);
        }
    }
    return 0;                                             /* unreached */
}

/* Create the hidden window + tray icon, start the file watcher, and run the message loop.
 * Returns when the user picks Close. */
static void run_tray(void) {
    WNDCLASSA wc; ZeroMemory(&wc, sizeof(wc));
    wc.lpfnWndProc   = tray_proc;
    wc.hInstance     = GetModuleHandleA(NULL);
    wc.lpszClassName = "gcalxpTray";
    RegisterClassA(&wc);
    g_tray_wnd = CreateWindowA("gcalxpTray", "gcal-xp", WS_OVERLAPPED, 0, 0, 0, 0, NULL, NULL, wc.hInstance, NULL);

    ZeroMemory(&g_nid, sizeof(g_nid));
    g_nid.cbSize           = sizeof(g_nid);
    g_nid.hWnd             = g_tray_wnd;
    g_nid.uID              = 1;
    g_nid.uFlags           = NIF_ICON | NIF_MESSAGE | NIF_TIP;
    g_nid.uCallbackMessage = WM_TRAY;
    g_nid.hIcon            = LoadIconA(NULL, (LPCSTR)IDI_APPLICATION);
    strcpy(g_nid.szTip, "gcal-xp - fake Google for Lucky*Mas");
    Shell_NotifyIconA(NIM_ADD, &g_nid);

    CreateThread(NULL, 0, watch_thread, NULL, 0, NULL);

    MSG msg;
    while (GetMessageA(&msg, NULL, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessageA(&msg);
    }
}

int main(int argc, char **argv) {
    int want_install = 0, want_tls = 1, want_cert = 1, want_install_cert = 0;
    for (int i = 1; i < argc; i++) {
        if      (!strcmp(argv[i], "--install"))      want_install = 1;
        else if (!strcmp(argv[i], "--install-cert")) want_install_cert = 1;
        else if (!strcmp(argv[i], "--no-tls"))     want_tls = 0;
        else if (!strcmp(argv[i], "--no-cert"))    want_cert = 0;
        else if (!strcmp(argv[i], "--no-tray"))    g_tray = 0;
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

    if (want_install_cert) {                 /* installer step: trust the cert (admin), then exit */
        int ok = tls_init() && cert_install_machine();
        logln("--install-cert: %s", ok ? "done" : "FAILED");
        return ok ? 0 : 1;
    }

    if (!lua_init()) { logln("FATAL: Lua init failed — no request logic"); return 1; }

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
    logln("gcalsrv ready (%d listener%s)%s", nt, nt == 1 ? "" : "s", g_tray ? ", tray UI" : " [headless]");
    if (g_tray) run_tray();                                  /* tray icon + hot-reload; returns on Close */
    else        WaitForMultipleObjects(nt, threads, TRUE, INFINITE);  /* headless: serve forever */
    return 0;
}
