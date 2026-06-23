-- gcalsrv.lua - request logic + YOUR calendar/mail content for the Lucky*Mas
-- native fake-Google server (gcalsrv.exe). Pure Lua 5.4 (stdlib only).
--
-- The C host (gcalsrv.c) owns sockets + Schannel TLS + POP3 line framing + the
-- HTTP/1.0 status line/headers; it calls in here for the *content*:
--   http_handle(method, path, query, body) -> status:int, ctype:string, body:string
--   pop3_event(verb, arg)                   -> reply:string|nil, action:"send"|"quit"|"drop"
-- C exposes:  gcalsrv_log(msg)   gcalsrv_exedir()
--
-- ============================================================================
--  * CUSTOMISE HERE - what the desktop mascots show. Edit + save; the server
--    re-reads this file on EVERY request (when run as the external
--    <exedir>\gcalsrv.lua, which overrides the copy baked into the EXE), so
--    there's no rebuild or restart - change it, then click the mascot again.
--
--  The launcher's right-click menu has "Check Schedule Now" / "Check Mail Now";
--  what the mascot finds picks her speech bubble:
--      calendar - today has event(s) -> SerifCallenderSchedule (she reads the titles)
--                 today is empty      -> SerifCallenderNone   ("no plans today")
--      mail     - unread > 0          -> SerifMailCheck       ("you've got mail")
--                 unread = 0          -> SerifMailNone
--  (To see the *error* bubbles, force them from gcal-xp.ini - see the foot of this file.)
-- ============================================================================

-- Your appointments, keyed by date "YYYY-MM-DD". Each day is a LIST of events;
-- an event is either a plain title string, or a table to add a time / place:
--     { title = "Dentist", at = "10:00", where = "Akihabara" }
-- The special key ["*"] is a WILDCARD shown on any day that has no entry of its own
-- (so there are demo events out of the box) - replace it with your own, or delete it
-- for "no plans unless I add the date". A specific date OVERRIDES the wildcard; a date
-- set to an empty list {} forces SerifCallenderNone for that day.
local EVENTS = {
  ["*"] = {                                           -- shown every day until you customise it
    { title = "Dentist",           at = "10:00", where = "Akihabara Clinic" },
    { title = "Lunch with Konata", at = "12:30" },
    "Buy doujinshi",                                  -- title only -> a default time slot
  },
  ["2026-12-30"] = {                                  -- a specific day overrides the wildcard
    { title = "Comiket 109 -- Day 1", at = "08:00", where = "Tokyo Big Sight" },
  },
}

-- Your inbox, keyed by date "YYYY-MM-DD" (["*"] = wildcard, same as above). Each day is
-- a LIST of messages; a message is { from = , subject = , body = } (or just a subject
-- string). The mascot only COUNTS them (Check vs None), but a real POP3 client on :110
-- can log in and RETR/read them - so this is a working fake mailbox, not just a count.
local MAIL = {
  ["*"] = {                                           -- demo inbox out of the box
    { from = "konata@lucky.example", subject = "new figs just dropped!!",
      body = "did you see the new nendoroid? we have to go saturday!!" },
    { from = "kagami@lucky.example", subject = "did you finish the homework",
      body = "...you didn't, did you." },
  },
}

-- Pretend "today" is this date (to preview a specific day's bubbles no matter
-- what the PC clock says). nil = use the real system date.
local TODAY = nil                         -- e.g. "2026-06-23"

-- Calendar identity shown in the feed. The launcher's account + password are
-- ignored (any login succeeds against this fake server), so these are cosmetic.
local ACCOUNT  = "you@lucky.example"
local CALNAME  = "My Calendar"
local TZOFFSET = "+09:00"                 -- your UTC offset, GData style

-- ============================================================================
--  Engine below - routing + the Google GData / POP3 wire formats. You usually
--  don't need to touch this; the data above is what you edit.
-- ============================================================================

local EXEDIR = (gcalsrv_exedir and gcalsrv_exedir()) or "."
local INI    = EXEDIR .. "\\gcal-xp.ini"

-- Optional gcal-xp.ini (key=value), re-read per request - lets a TEST HARNESS
-- force a scenario without editing this script. All keys are optional:
--   calendar = none | error           -- else: the EVENTS table drives the day
--   mail     = none | error | refuse  -- else: the MAIL table drives the day
--   today    = YYYY-MM-DD             -- override the date (like TODAY above)
--   account / calname / tzoffset      -- override the identity above
--   events   = A;B;C                  -- override EVENTS for ALL days (flat list)
--   mailcount = N                     -- override the unread count
local function load_ini()
  local c = {}
  local f = io.open(INI, "r")
  if f then
    for line in f:lines() do
      if not line:match("^%s*[#;]") then
        local k, v = line:match("^%s*([%w_]+)%s*=%s*(.-)%s*$")
        if k then c[k] = v end
      end
    end
    f:close()
  end
  return c
end

local function today_str(ini) return ini.today or TODAY or os.date("%Y-%m-%d") end

local ESC = { ["&"] = "&amp;", ["<"] = "&lt;", [">"] = "&gt;", ['"'] = "&quot;" }
local function xesc(s) return (tostring(s):gsub('[&<>"]', ESC)) end

-- percent-encode / decode for the click-through URLs below
local function urlenc(s)
  return (tostring(s):gsub("[^%w%-%._~]", function(c) return ("%%%02X"):format(c:byte()) end))
end
local function urldec(s)
  return (tostring(s):gsub("+", " "):gsub("%%(%x%x)", function(h) return string.char(tonumber(h, 16)) end))
end

-- A per-event alternate link. gcal.exe reads <link rel='alternate'>'s href into the event and uses
-- it for TWO things: the ShellExecute target when you click the event, AND the per-weekday-column
-- row key in the month grid -- so without a UNIQUE href every event collapses onto ONE line and a
-- click opens the app folder. We hand each event a unique localhost URL in the same add-event
-- TEMPLATE shape gcal.exe builds itself, so a click opens our /calendar/event page (below).
local function event_link(ini, gy, gm, gd, title, where, idx)
  local ymd = ("%04d%02d%02d"):format(gy, gm, gd)
  local q = ("action=TEMPLATE&dates=%s/%s&text=%s&i=%d"):format(ymd, ymd, urlenc(title), idx)
  if where and where ~= "" then q = q .. "&location=" .. urlenc(where) end
  return {
    href = "http://localhost/calendar/event?" .. q,
    id   = ("tag:localhost,2007:event/%s/%s/%d"):format(ini.account or ACCOUNT, ymd, idx),
  }
end

local ATOM_NS =
  "xmlns='http://www.w3.org/2005/Atom' " ..
  "xmlns:gd='http://schemas.google.com/g/2005' " ..
  "xmlns:gCal='http://schemas.google.com/gCal/2005'"
local ATOM = "application/atom+xml; charset=UTF-8"

local function feed_head(title)
  return { "<?xml version='1.0' encoding='UTF-8'?>", "<feed " .. ATOM_NS .. ">",
           "  <title type='text'>" .. xesc(title) .. "</title>" }
end

-- title-only events rotate through these start times (minutes-of-day)
local DEFAULT_SLOTS = { 9 * 60, 12 * 60 + 30, 15 * 60, 18 * 60 }
local function norm_event(e, idx)
  local title, at, where
  if type(e) == "table" then title, where, at = e.title or "", e.where, e.at
  else title = tostring(e) end
  local mins
  if at then local h, m = at:match("(%d+):(%d+)"); if h then mins = tonumber(h) * 60 + tonumber(m) end end
  mins = mins or DEFAULT_SLOTS[(idx - 1) % #DEFAULT_SLOTS + 1]
  return title, mins, where
end

-- The launcher's day-bubble asks for one day (start-min..start-max = today..tomorrow); the gcal.exe
-- month grid asks for a whole month (e.g. 06-01..07-01). We must place each event on its OWN date
-- across that window -- NOT pile them all on start-min (that was the "everything on the 1st" bug).
local function in_window(k, lo, hi)   -- [lo,hi) exclusive; nil hi, or a same-day range, = just `lo`
  if hi and hi > lo then return k >= lo and k < hi else return k == lo end
end

-- {date=YYYY-MM-DD, evs=list} groups to render for the requested window. Specific dates render on
-- their own day; the ["*"] wildcard is the demo fallback and renders ONLY on "today" (so a month
-- grid shows the demo events on the current day, not duplicated onto every day).
local function collect_events(ini, query)
  local q = query or ""
  local lo = q:match("start%-min=(%d%d%d%d%-%d%d%-%d%d)") or today_str(ini)
  local hi = q:match("start%-max=(%d%d%d%d%-%d%d%-%d%d)")        -- exclusive; nil = just `lo`
  local today = today_str(ini)
  local groups = {}
  if ini.events then                                            -- test override: flat list on "today"
    if in_window(today, lo, hi) then
      local t = {}
      for tok in (ini.events .. ";"):gmatch("(.-);") do
        tok = tok:match("^%s*(.-)%s*$"); if tok ~= "" then t[#t + 1] = tok end
      end
      groups[#groups + 1] = { date = today, evs = t }
    end
    return groups
  end
  for k, evs in pairs(EVENTS) do
    if k ~= "*" and k:match("^%d%d%d%d%-%d%d%-%d%d$") and in_window(k, lo, hi) then
      groups[#groups + 1] = { date = k, evs = evs }
    end
  end
  if EVENTS["*"] and not EVENTS[today] and in_window(today, lo, hi) then
    groups[#groups + 1] = { date = today, evs = EVENTS["*"] }
  end
  table.sort(groups, function(a, b) return a.date < b.date end)
  return groups
end

local function allcalendars(ini)
  local href = ("http://localhost/calendar/feeds/%s/private/full"):format(ini.account or ACCOUNT)
  local out = feed_head("Calendar List")
  out[#out + 1] = "  <entry>"
  out[#out + 1] = "    <title type='text'>" .. xesc(ini.calname or CALNAME) .. "</title>"
  out[#out + 1] = "    <link rel='alternate' type='application/atom+xml' href='" .. xesc(href) .. "'/>"
  out[#out + 1] = "    <gCal:color value='#2952A3'/>"
  out[#out + 1] = "    <gCal:accesslevel value='owner'/>"
  out[#out + 1] = "    <gCal:selected value='true'/>"
  out[#out + 1] = "  </entry>"
  out[#out + 1] = "</feed>"; out[#out + 1] = ""
  return table.concat(out, "\n")
end

-- no groups -> a feed with no <entry> -> the parser counts 0 -> None bubble
local function events_feed(ini, groups)
  local tz = ini.tzoffset or TZOFFSET
  local out = feed_head(ini.calname or CALNAME)
  for _, g in ipairs(groups) do
    local gy, gm, gd = g.date:match("(%d+)-(%d+)-(%d+)")
    gy, gm, gd = tonumber(gy), tonumber(gm), tonumber(gd)
    for i, e in ipairs(g.evs) do
      local title, mins, where = norm_event(e, i)
      local sh, sm = mins // 60, mins % 60
      local eh, em = (mins + 60) // 60, (mins + 60) % 60
      out[#out + 1] = "  <entry>"
      out[#out + 1] = "    <title type='text'>" .. xesc(title) .. "</title>"
      out[#out + 1] = "    <content type='text'>" .. xesc(title) .. "</content>"
      local lnk = event_link(ini, gy, gm, gd, title, where, i)
      out[#out + 1] = "    <id>" .. xesc(lnk.id) .. "</id>"
      out[#out + 1] = "    <link rel='alternate' type='text/html' href='" .. xesc(lnk.href) .. "'/>"
      out[#out + 1] = ("    <gd:when startTime='%04d-%02d-%02dT%02d:%02d:00.000%s' " ..
                       "endTime='%04d-%02d-%02dT%02d:%02d:00.000%s'/>")
                      :format(gy, gm, gd, sh, sm, tz, gy, gm, gd, eh, em, tz)
      if where then out[#out + 1] = "    <gd:where valueString='" .. xesc(where) .. "'/>" end
      out[#out + 1] = "    <gd:eventStatus value='http://schemas.google.com/g/2005#event.confirmed'/>"
      out[#out + 1] = "  </entry>"
    end
  end
  out[#out + 1] = "</feed>"; out[#out + 1] = ""
  return table.concat(out, "\n")
end

-- Render the /calendar/event page (the add-event TEMPLATE target): used both by gcal.exe's own
-- click-a-day-to-add affordance and by our per-event links, so it just reflects the query back.
local function event_page(query)
  local p = {}
  for k, v in (query or ""):gmatch("([^&=]+)=([^&]*)") do p[k] = urldec(v) end
  local d = p.dates and p.dates:match("^(%d%d%d%d%d%d%d%d)") or ""
  local date = (#d == 8) and (d:sub(1, 4) .. "-" .. d:sub(5, 6) .. "-" .. d:sub(7, 8)) or (p.dates or "")
  local title = (p.text and p.text ~= "") and p.text or "(untitled)"
  local rows = { { "Title", title }, { "Date", date } }
  if p.location and p.location ~= "" then rows[#rows + 1] = { "Where", p.location } end
  local out = { "<!DOCTYPE html><html><head><meta http-equiv='Content-Type' content='text/html; charset=UTF-8'><title>", xesc(title),
                "</title></head><body><h2>", xesc(title), "</h2><table>" }
  for _, r in ipairs(rows) do
    out[#out + 1] = "<tr><td><b>" .. xesc(r[1]) .. ":</b></td><td>" .. xesc(r[2]) .. "</td></tr>"
  end
  out[#out + 1] = "</table><p><small>gcal-xp local calendar</small></p></body></html>"
  return table.concat(out)
end

function http_handle(method, path, query, body)
  local ini = load_ini()
  path = path:gsub("/+$", "")
  local cal_err = (ini.calendar == "error")
  if method == "POST" and path == "/accounts/ClientLogin" then
    if cal_err then return 403, "text/plain; charset=UTF-8", "Error=BadAuthentication\n" end
    return 200, "text/plain; charset=UTF-8", "SID=emu\nLSID=emu\nAuth=EMU_TEST_TOKEN\n"
  elseif method == "GET" and path == "/calendar/feeds/default/allcalendars/full" then
    if cal_err then return 403, "text/plain", "Forbidden\n" end
    return 200, ATOM, allcalendars(ini)
  elseif method == "GET" and path:sub(1, 16) == "/calendar/feeds/" then
    if cal_err then return 403, "text/plain", "Forbidden\n" end
    local groups = (ini.calendar == "none") and {} or collect_events(ini, query)
    return 200, ATOM, events_feed(ini, groups)
  elseif method == "GET" and path == "/calendar/event" then
    return 200, "text/html; charset=UTF-8", event_page(query)
  end
  return 404, "text/plain", "Not Found\n"
end

-- the inbox for "today" (server date or override); ini `mailcount` overrides the count
local function inbox(ini)
  if ini.mailcount then
    local n = math.tointeger(tonumber(ini.mailcount)) or 0
    local t = {}
    for i = 1, (n < 0 and 0 or n) do t[i] = { from = "sender@example", subject = "Message " .. i } end
    return t
  end
  return MAIL[today_str(ini)] or MAIL["*"] or {}
end

local function msg_text(msg, i)
  local from = (type(msg) == "table" and msg.from) or "noreply@lucky.example"
  local subj = (type(msg) == "table" and msg.subject) or tostring(msg)
  local body = (type(msg) == "table" and msg.body) or ""
  return ("From: %s\r\nTo: you@lucky.example\r\nSubject: %s\r\nMessage-ID: <msg%04d@gcal-xp>\r\n\r\n%s")
         :format(from, subj, i, body)
end

-- POP3: C calls this once per command (verb upper-cased; "CONNECT" = new session).
-- Returns (reply, action); reply may be multi-line (\r\n-joined), C adds the final CRLF.
function pop3_event(verb, arg)
  local ini = load_ini()
  if verb == "CONNECT" then
    if ini.mail == "refuse" then return nil, "drop" end
    return "+OK gcal-xp POP3 ready", "send"
  end
  local box = (ini.mail == "none") and {} or inbox(ini)
  local n = #box
  local total = 0
  for i = 1, n do total = total + #msg_text(box[i], i) end
  if verb == "USER" then
    return "+OK user accepted", "send"
  elseif verb == "PASS" then
    if ini.mail == "error" then return "-ERR [AUTH] authentication failed", "send" end
    return "+OK mailbox ready", "send"
  elseif verb == "STAT" then                              -- n>0 -> SerifMailCheck, n=0 -> SerifMailNone
    return ("+OK %d %d"):format(n, total), "send"
  elseif verb == "LIST" then
    local t = { ("+OK %d messages (%d octets)"):format(n, total) }
    for i = 1, n do t[#t + 1] = ("%d %d"):format(i, #msg_text(box[i], i)) end
    t[#t + 1] = "."
    return table.concat(t, "\r\n"), "send"
  elseif verb == "UIDL" then
    local t = { "+OK" }
    for i = 1, n do t[#t + 1] = ("%d msg%04d"):format(i, i) end
    t[#t + 1] = "."
    return table.concat(t, "\r\n"), "send"
  elseif verb == "RETR" then                              -- a real mail client can read the fake messages
    local i = math.tointeger(tonumber(arg)) or 0
    if i < 1 or i > n then return "-ERR no such message", "send" end
    local m = msg_text(box[i], i)
    return ("+OK %d octets\r\n%s\r\n."):format(#m, m), "send"
  elseif verb == "TOP" then
    local i = math.tointeger(tonumber((arg or ""):match("^(%d+)"))) or 0
    if i < 1 or i > n then return "-ERR no such message", "send" end
    local hdr = msg_text(box[i], i):match("^(.-)\r\n\r\n") or ""
    return ("+OK\r\n%s\r\n."):format(hdr), "send"
  elseif verb == "DELE" then
    return "+OK message deleted (no-op)", "send"
  elseif verb == "RSET" then
    return "+OK", "send"
  elseif verb == "CAPA" then
    return "-ERR no capabilities", "send"
  elseif verb == "QUIT" then
    return "+OK bye", "quit"
  elseif verb == "NOOP" then
    return "+OK", "send"
  end
  return "-ERR unknown command", "send"
end
