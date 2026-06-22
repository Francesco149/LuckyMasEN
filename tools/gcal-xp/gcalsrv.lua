-- gcalsrv.lua — request logic for the らき☆マス native fake-Google server.
--
-- The C host (gcalsrv.c) owns sockets + Schannel TLS + POP3 line framing and the
-- HTTP/1.0 status-line/headers; it calls into here for the *content*:
--   http_handle(method, path, query, body)  -> status:int, ctype:string, body:string
--   pop3_event(verb, arg)                    -> reply:string|nil, action:"send"|"quit"|"drop"
-- C exposes:  gcalsrv_log(msg)   gcalsrv_exedir()
--
-- This is loaded from <exedir>\gcalsrv.lua if present (customise freely — e.g. a real
-- local-calendar backend), else from the copy embedded in the EXE. Pure Lua 5.4 stdlib.
-- Responses match the gcal_emu.py oracle; scenario knobs come from gcal-xp.ini.

local EXEDIR = (gcalsrv_exedir and gcalsrv_exedir()) or "."
local INI    = EXEDIR .. "\\gcal-xp.ini"

local DEFAULTS = {
  calendar  = "schedule",                              -- schedule | none | error
  mail      = "check",                                 -- check | none | error | refuse
  account   = "test@example.com",
  calname   = "Test Calendar",
  tzoffset  = "+09:00",
  events    = "Dentist;Lunch with Konata;Buy doujinshi",
  mailcount = "3",
}

-- gcal-xp.ini (key=value), re-read per request so the bubble can be flipped live.
local function load_cfg()
  local c = {}
  for k, v in pairs(DEFAULTS) do c[k] = v end
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

local ESC = { ["&"] = "&amp;", ["<"] = "&lt;", [">"] = "&gt;", ['"'] = "&quot;" }
local function xesc(s) return (tostring(s):gsub('[&<>"]', ESC)) end

local ATOM_NS =
  "xmlns='http://www.w3.org/2005/Atom' " ..
  "xmlns:gd='http://schemas.google.com/g/2005' " ..
  "xmlns:gCal='http://schemas.google.com/gCal/2005'"

-- ';'-separated, space-trimmed, non-empty titles
local function split_events(s)
  local t = {}
  for tok in (s .. ";"):gmatch("(.-);") do
    tok = tok:match("^%s*(.-)%s*$")
    if tok ~= "" then t[#t + 1] = tok end
  end
  return t
end

-- the day the launcher asks about: GData start-min if present, else local today
local function anchor_date(query)
  local y, m, d = (query or ""):match("start%-min=(%d%d%d%d)%-(%d%d)%-(%d%d)")
  if y then return tonumber(y), tonumber(m), tonumber(d) end
  local t = os.date("*t")
  return t.year, t.month, t.day
end

local function allcalendars(c)
  local href = ("http://www.google.com/calendar/feeds/%s/private/full"):format(c.account)
  return table.concat({
    "<?xml version='1.0' encoding='UTF-8'?>",
    "<feed " .. ATOM_NS .. ">",
    "  <title type='text'>Calendar List</title>",
    "  <entry>",
    "    <title type='text'>" .. xesc(c.calname) .. "</title>",
    "    <link rel='alternate' type='application/atom+xml' href='" .. xesc(href) .. "'/>",
    "    <gCal:color value='#2952A3'/>",
    "    <gCal:accesslevel value='owner'/>",
    "    <gCal:selected value='true'/>",
    "  </entry>",
    "</feed>", "",
  }, "\n")
end

local SLOTS = { { 9, 0, 10, 0 }, { 12, 30, 13, 30 }, { 15, 0, 16, 0 }, { 18, 0, 19, 0 } }

local function events_feed(c, query)
  local y, m, d = anchor_date(query)
  local out = {
    "<?xml version='1.0' encoding='UTF-8'?>",
    "<feed " .. ATOM_NS .. ">",
    "  <title type='text'>" .. xesc(c.calname) .. "</title>",
  }
  for i, t in ipairs(split_events(c.events)) do
    local s = SLOTS[(i - 1) % 4 + 1]
    out[#out + 1] = "  <entry>"
    out[#out + 1] = "    <title type='text'>" .. xesc(t) .. "</title>"
    out[#out + 1] = "    <content type='text'>" .. xesc(t) .. "</content>"
    out[#out + 1] = ("    <gd:when startTime='%04d-%02d-%02dT%02d:%02d:00.000%s' " ..
                     "endTime='%04d-%02d-%02dT%02d:%02d:00.000%s'/>")
                    :format(y, m, d, s[1], s[2], c.tzoffset, y, m, d, s[3], s[4], c.tzoffset)
    out[#out + 1] = "    <gd:where valueString='Akihabara'/>"
    out[#out + 1] = "    <gd:eventStatus value='http://schemas.google.com/g/2005#event.confirmed'/>"
    out[#out + 1] = "  </entry>"
  end
  out[#out + 1] = "</feed>"
  out[#out + 1] = ""
  return table.concat(out, "\n")
end

local function empty_feed(c)
  return table.concat({
    "<?xml version='1.0' encoding='UTF-8'?>",
    "<feed " .. ATOM_NS .. ">",
    "  <title type='text'>" .. xesc(c.calname) .. "</title>",
    "</feed>", "",
  }, "\n")
end

local ATOM = "application/atom+xml; charset=UTF-8"

function http_handle(method, path, query, body)
  local c = load_cfg()
  path = path:gsub("/+$", "")                          -- strip trailing slashes
  if method == "POST" and path == "/accounts/ClientLogin" then
    if c.calendar == "error" then return 403, "text/plain; charset=UTF-8", "Error=BadAuthentication\n" end
    return 200, "text/plain; charset=UTF-8", "SID=emu\nLSID=emu\nAuth=EMU_TEST_TOKEN\n"
  elseif method == "GET" and path == "/calendar/feeds/default/allcalendars/full" then
    if c.calendar == "error" then return 403, "text/plain", "Forbidden\n" end
    return 200, ATOM, allcalendars(c)
  elseif method == "GET" and path:sub(1, 16) == "/calendar/feeds/" then
    if c.calendar == "error" then return 403, "text/plain", "Forbidden\n" end
    local n = (c.calendar == "none") and 0 or #split_events(c.events)
    return 200, ATOM, (n > 0) and events_feed(c, query) or empty_feed(c)
  elseif method == "GET" and path == "/calendar/event" then
    return 200, "text/html", "<html><body>gcal-xp: add-event template (no-op stub)</body></html>"
  end
  return 404, "text/plain", "Not Found\n"
end

-- POP3: called once per command (verb is upper-cased by C; "CONNECT" = new session).
-- Returns (reply, action); reply may be multi-line (\r\n-joined); C appends the final CRLF.
function pop3_event(verb, arg)
  local c = load_cfg()
  if verb == "CONNECT" then
    if c.mail == "refuse" then return nil, "drop" end
    return "+OK gcal-xp POP3 ready", "send"
  end
  local n = (c.mail == "check") and (math.tointeger(tonumber(c.mailcount)) or 0) or 0
  if n < 0 then n = 0 end
  local size = n * 1024
  if verb == "USER" then
    return "+OK user accepted", "send"
  elseif verb == "PASS" then
    if c.mail == "error" then return "-ERR [AUTH] authentication failed", "send" end
    return "+OK mailbox ready", "send"
  elseif verb == "STAT" then
    return ("+OK %d %d"):format(n, size), "send"
  elseif verb == "LIST" then
    local t = { ("+OK %d messages (%d octets)"):format(n, size) }
    for i = 1, n do t[#t + 1] = ("%d 1024"):format(i) end
    t[#t + 1] = "."
    return table.concat(t, "\r\n"), "send"
  elseif verb == "UIDL" then
    local t = { "+OK" }
    for i = 1, n do t[#t + 1] = ("%d msg%04d"):format(i, i) end
    t[#t + 1] = "."
    return table.concat(t, "\r\n"), "send"
  elseif verb == "CAPA" then
    return "-ERR no capabilities", "send"
  elseif verb == "QUIT" then
    return "+OK bye", "quit"
  elseif verb == "NOOP" then
    return "+OK", "send"
  end
  return "-ERR unknown command", "send"
end
