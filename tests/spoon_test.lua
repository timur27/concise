-- Plain-Lua tests for Concise.spoon; no Hammerspoon needed. Run from the repo root: lua tests/spoon_test.lua
local SPOON = "Concise.spoon/"

local failures, count = 0, 0
local function test(name, fn)
  count = count + 1
  local ok, err = pcall(fn)
  if not ok then
    failures = failures + 1
    print("FAIL " .. name .. ": " .. tostring(err))
  end
end

local function eq(actual, expected, msg)
  if actual ~= expected then
    error(string.format("%sexpected %s, got %s", msg and (msg .. ": ") or "", tostring(expected), tostring(actual)), 2)
  end
end

-- Segmenter ------------------------------------------------------------------

local Segmenter = dofile(SPOON .. "segmenter.lua")

-- Types a string; "\b" is backspace, "\n" is Enter, "|" is a pause long enough to fire the timer.
local function typeInto(seg, keys)
  local out = {}
  local function emit(s) if s then out[#out + 1] = s end end
  for c in keys:gmatch(utf8.charpattern) do
    if c == "\b" then seg:backspace()
    elseif c == "\n" then emit(seg:enter())
    elseif c == "|" then emit(seg:pauseElapsed())
    else emit(seg:feed(c)) end
  end
  return out
end

local SEGMENTER_CASES = {
  {"space after a full stop ends the sentence", "This is short. Next", {"This is short."}},
  {"question and exclamation marks", "Is this ok? Yes it is! ", {"Is this ok?", "Yes it is!"}},
  {"abbreviation does not end it", "Use tools e.g. hammers here. ", {"Use tools e.g. hammers here."}},
  {"abbreviation check ignores case and quotes", "Ask (Dr. Smith) today please. ", {"Ask (Dr. Smith) today please."}},
  {"closing quote keeps the end pending", 'He said "stop now." Then', {'He said "stop now."'}},
  {"fewer than three words is skipped", "Too short. ", {}},
  {"a pause ends the sentence", "This is short.|", {"This is short."}},
  {"a pause without an end mark does nothing", "This is short|", {}},
  {"Enter ends a pending sentence", "This is short.\n", {"This is short."}},
  {"Enter without an end mark discards the buffer", "This is short\nNow it ends. ", {"Now it ends."}},
  {"backspace over the end mark cancels it", "This is short.\b and longer. ", {"This is short and longer."}},
  {"backspace back to an end mark re-arms it", "This is short.x\b ", {"This is short."}},
  {"backspace removes whole UTF-8 characters", "Café nice é\b day. ", {"Café nice  day."}},
  {"a letter right after the mark continues", "Version 1.5 is out now. ", {"Version 1.5 is out now."}},
}

for _, case in ipairs(SEGMENTER_CASES) do
  test("segmenter: " .. case[1], function()
    local got = typeInto(Segmenter.new(), case[2])
    eq(#got, #case[3], "sentence count (" .. table.concat(got, " | ") .. ")")
    for i, s in ipairs(case[3]) do eq(got[i], s) end
  end)
end

test("segmenter: buffer is capped", function()
  local seg = Segmenter.new({maxBuffer = 10})
  typeInto(seg, string.rep("a", 25))
  eq(#seg.buf, 10)
end)

test("segmenter: reset clears the pending mark", function()
  local seg = Segmenter.new()
  typeInto(seg, "This is short.")
  eq(seg:isPending(), true)
  seg:reset()
  eq(seg:isPending(), false)
  eq(seg:pauseElapsed(), nil)
end)

test("segmenter: options", function()
  local got = typeInto(Segmenter.new({minWords = 1, abbreviations = {"approx."}}), "Hi. It is approx. done. ")
  eq(#got, 2)
  eq(got[2], "It is approx. done.")
end)

-- Key classification ---------------------------------------------------------

local AutoCheck = dofile(SPOON .. "autocheck.lua")
local MAP = {tab = 48, escape = 53, left = 123, right = 124, up = 126, down = 125, home = 115, ["end"] = 119,
  pageup = 116, pagedown = 121, forwarddelete = 117, ["return"] = 36, padenter = 76, delete = 51}
local CODES = AutoCheck.keyCodes(MAP)

test("classify: keys", function()
  eq(AutoCheck.classify({}, 36, "\r", CODES), "enter")
  eq(AutoCheck.classify({}, 76, "\3", CODES), "enter")
  eq(AutoCheck.classify({}, 51, "\8", CODES), "backspace")
  eq(AutoCheck.classify({alt = true}, 51, "", CODES), "reset")
  eq(AutoCheck.classify({cmd = true}, 0, "a", CODES), "reset")
  eq(AutoCheck.classify({ctrl = true}, 0, "a", CODES), "reset")
  eq(AutoCheck.classify({}, 123, "", CODES), "reset")
  eq(AutoCheck.classify({}, 117, "", CODES), "reset")
  eq(AutoCheck.classify({}, 0, "", CODES), nil)
  local action, text = AutoCheck.classify({shift = true}, 0, "A", CODES)
  eq(action, "text")
  eq(text, "A")
end)

-- Client -----------------------------------------------------------------------

local Client = dofile(SPOON .. "client.lua")

-- The fake decoder maps known bodies to tables, standing in for hs.json.decode.
local BODIES = {
  ok = {score = 0.8, good = true, threshold = 0.5, ms = 12},
  too_large = {error = {code = "too_large", message = "text longer than 10000 bytes"}},
  failed = {error = {code = "model_failed", message = "prediction failed"}},
  health = {status = "ok", api = 1, backend = "base", max_bytes = 10000},
  shapeless = {hello = "world"},
}
local function decode(body)
  if BODIES[body] == nil then error("bad json") end
  return BODIES[body]
end

local function fakeClient(status, body)
  local http = {}
  function http.asyncPost(url, data, headers, cb) http.url = url; cb(status, body) end
  function http.asyncGet(url, headers, cb) http.url = url; cb(status, body) end
  return Client.new({url = "http://127.0.0.1:8765/", http = http, decode = decode}), http
end

local function scoreWith(status, body)
  local client, http = fakeClient(status, body)
  local err, result
  client:score("Some text.", function(e, r) err, result = e, r end)
  return err, result, http.url
end

test("client: success", function()
  local err, r, url = scoreWith(200, "ok")
  eq(err, nil)
  eq(r.score, 0.8)
  eq(r.good, true)
  eq(url, "http://127.0.0.1:8765/v1/score")
end)

test("client: typed errors", function()
  local cases = {
    {-1, nil, "unreachable", "concise server not running at http://127.0.0.1:8765"},
    {413, "too_large", "rejected", "text longer than 10000 bytes"},
    {500, "failed", "server", "prediction failed"},
    {200, "shapeless", "protocol", "unexpected reply from concise server (HTTP 200)"},
    {200, "not json", "protocol", nil},
    {502, "<html>", "protocol", nil},
  }
  for _, c in ipairs(cases) do
    local err = scoreWith(c[1], c[2])
    eq(err and err.kind, c[3], "status " .. c[1])
    if c[4] then eq(err.message, c[4]) end
  end
  eq(scoreWith(413, "too_large").code, "too_large")
end)

test("client: health", function()
  local client, http = fakeClient(200, "health")
  local info
  client:health(function(_, i) info = i end)
  eq(info.api, 1)
  eq(http.url, "http://127.0.0.1:8765/v1/health")
  local err
  fakeClient(501, "<html>"):health(function(e) err = e end)
  eq(err.kind, "protocol")
end)

-- Capture ----------------------------------------------------------------------

local Capture = dofile(SPOON .. "capture.lua")

test("capture: concealed clipboard types", function()
  eq(Capture.isConcealed({["public.utf8-plain-text"] = "x"}), false)
  eq(Capture.isConcealed({["org.nspasteboard.ConcealedType"] = ""}), true)
  eq(Capture.isConcealed({["org.nspasteboard.TransientType"] = ""}), true)
end)

-- Spoon lifecycle with a fake hs --------------------------------------------------

local function fakeHs()
  local live = {menubars = 0, taps = 0, hotkeys = 0, alerts = {}, settings = {}, front = nil, timers = {}}
  local function tap()
    local t = {on = false}
    function t:start() if not self.on then live.taps = live.taps + 1 end self.on = true end
    function t:stop() if self.on then live.taps = live.taps - 1 end self.on = false end
    return t
  end
  local fake = {
    _live = live,
    spoons = {resourcePath = function(f) return SPOON .. f end},
    logger = {new = function() return {i = function() end, w = function() end} end},
    keycodes = {map = MAP},
    alert = {show = function(msg) live.alerts[#live.alerts + 1] = msg end},
    settings = {get = function(k) return live.settings[k] end, set = function(k, v) live.settings[k] = v end},
    timer = {delayed = {new = function(_, fn)
      local t = {fn = fn}
      function t:start() live.timers[#live.timers + 1] = self end
      function t:stop() end
      return t
    end}},
    eventtap = {new = function() return tap() end, event = {types = {keyDown = 10, leftMouseDown = 1}}},
    application = {
      frontmostApplication = function() return live.front end,
      watcher = {activated = 5, new = function() return tap() end},
    },
    hotkey = {new = function()
      local h = {on = false}
      function h:enable() if not self.on then live.hotkeys = live.hotkeys + 1 end self.on = true end
      function h:disable() if self.on then live.hotkeys = live.hotkeys - 1 end self.on = false end
      function h:delete() self:disable() end
      return h
    end},
    menubar = {new = function()
      live.menubars = live.menubars + 1
      local m = {}
      function m:setClickCallback() end
      function m:setTitle(t) self.title = t end
      function m:setTooltip(t) self.tooltip = t end
      function m:delete() live.menubars = live.menubars - 1 end
      live.menu = m
      return m
    end},
    http = {
      asyncGet = function(_, _, cb) cb(-1, nil) end,
      asyncPost = function(_, _, _, cb) cb(live.status or -1, live.body) end,
    },
    json = {decode = decode},
  }
  return fake
end

local function app(bundleID) return {bundleID = function() return bundleID end} end

local function newSpoon()
  _G.hs = fakeHs()
  local spoon = dofile(SPOON .. "init.lua")
  spoon:init()
  return spoon, hs._live
end

test("spoon: start, stop and start again leaves one menu bar item", function()
  local spoon, live = newSpoon()
  spoon:bindHotkeys(spoon.defaultHotkeys)
  eq(live.hotkeys, 0, "hotkeys before start")
  spoon:start()
  spoon:start()
  eq(live.menubars, 1)
  eq(live.hotkeys, 2)
  eq(live.menu.tooltip, "Concise auto-check in Notes and VS Code (Ctrl+Option+K)")
  spoon:stop()
  eq(live.menubars, 0)
  eq(live.hotkeys, 0)
  spoon:start()
  eq(live.menubars, 1)
  eq(live.hotkeys, 2)
end)

test("spoon: taps run only with auto-check on and an allowed app in front", function()
  local spoon, live = newSpoon()
  live.front = app("com.apple.Terminal")
  spoon:start()
  spoon:setAuto(true)
  eq(live.taps, 1, "watcher only")
  spoon:stop()
  live.front = app("com.apple.Notes")
  spoon:start()
  eq(live.settings["concise.auto"], true)
  eq(live.taps, 3, "watcher and both taps")
  eq(live.menu.title, "ON")
  spoon:stop()
  eq(live.taps, 0, "all stopped")
end)

test("spoon: auto-check rate-limits error alerts but shows results", function()
  local spoon, live = newSpoon()
  spoon:start()
  spoon:setAuto(true)
  live.alerts = {}
  spoon:_onSentence("One two three.")
  spoon:_onSentence("One two three.")
  eq(#live.alerts, 1, "down alert shown once")
  eq(live.menu.title, "ON ?")
  live.status, live.body = 200, "ok"
  spoon:_onSentence("One two three.")
  eq(live.alerts[2], "0.80  ✓ concise")
  eq(live.menu.title, "ON ✓0.80")
end)

test("spoon: several servers are labelled", function()
  local spoon, live = newSpoon()
  spoon.servers = {{name = "Base", url = "http://a"}, {name = "Tuned", url = "http://b"}}
  live.status, live.body = 200, "ok"
  spoon:start()
  live.alerts = {}
  spoon:_scoreAll("One two three.", false)
  eq(live.alerts[1], "Base: 0.80  ✓ concise")
  eq(live.alerts[2], "Tuned: 0.80  ✓ concise")
end)

_G.hs = nil
print(string.format("%d tests, %d failed", count, failures))
os.exit(failures == 0 and 0 or 1)
