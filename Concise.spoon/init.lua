--- === Concise ===
---
--- Scores whether a sentence is concise, using a local concise server (see PROTOCOL.md).
--- Ctrl+Option+C scores the selection; Ctrl+Option+K or the menu bar item toggles auto-check,
--- which scores each sentence as you finish typing it in the allowed apps.
---
--- Usage, from ~/.hammerspoon/init.lua:
---   hs.loadSpoon("Concise")
---   spoon.Concise:bindHotkeys(spoon.Concise.defaultHotkeys)
---   spoon.Concise:start()

local function loadFile(file) return dofile(hs.spoons.resourcePath(file)) end
local Segmenter = loadFile("segmenter.lua")
local Client = loadFile("client.lua")
local Capture = loadFile("capture.lua")
local AutoCheck = loadFile("autocheck.lua")

local obj = {}
obj.__index = obj
obj.name = "Concise"
obj.version = "1.0"
obj.license = "MIT - https://opensource.org/licenses/MIT"

-- Configuration: change these fields before start().
-- Servers to score against; give each a name when there are several, to label the results.
obj.servers = {{url = "http://127.0.0.1:8765"}}
-- Auto-check only listens while one of these apps is in front (bundle ID -> display name). The hotkey works everywhere.
obj.apps = {["com.microsoft.VSCode"] = "VS Code", ["com.apple.Notes"] = "Notes"}
obj.pauseSeconds = 1.5
obj.minWords = 3
obj.maxBuffer = 1000
obj.abbreviations = Segmenter.DEFAULT_ABBREVIATIONS
obj.errorAlertInterval = 60
-- Debug aid: alert each detected sentence instead of scoring it. This shows typed text on screen.
obj.showSentences = false
obj.settingsKey = "concise.auto"
obj.defaultHotkeys = {score = {{"ctrl", "alt"}, "C"}, toggleAuto = {{"ctrl", "alt"}, "K"}}

obj.logger = hs.logger.new("concise", "info")

function obj:init()
  self._hotkeys = {}
  self._hotkeySpecs = {}
  self._running = false
end

local MOD_NAMES = {cmd = "Cmd", ctrl = "Ctrl", alt = "Option", shift = "Shift"}

local function describeHotkey(spec)
  if not spec then return nil end
  local parts = {}
  for _, m in ipairs(spec[1]) do parts[#parts + 1] = MOD_NAMES[m] or m end
  parts[#parts + 1] = spec[2]:upper()
  return table.concat(parts, "+")
end

local function formatResult(r)
  return string.format("%.2f  %s", r.score, r.good and "✓ concise" or "✗ wordy")
end

local function formatCompact(r)
  return string.format("%s%.2f", r.good and "✓" or "✗", r.score)
end

--- Concise:bindHotkeys(mapping)
--- Method
--- Binds hotkeys. mapping has optional `score` and `toggleAuto` entries, each {mods, key}.
function obj:bindHotkeys(mapping)
  for _, hk in pairs(self._hotkeys) do hk:delete() end
  self._hotkeys = {}
  self._hotkeySpecs = mapping
  if mapping.score then
    -- Fires on release: the copy waits for the modifiers to go up anyway.
    self._hotkeys.score = hs.hotkey.new(mapping.score[1], mapping.score[2], nil, function() self:scoreSelection() end)
  end
  if mapping.toggleAuto then
    self._hotkeys.toggleAuto = hs.hotkey.new(mapping.toggleAuto[1], mapping.toggleAuto[2], function() self:toggleAuto() end)
  end
  if self._running then
    for _, hk in pairs(self._hotkeys) do hk:enable() end
    self:_updateMenu()
  end
  return self
end

--- Concise:start()
--- Method
--- Shows the menu bar item, enables the hotkeys and restores the saved auto-check state.
function obj:start()
  if self._running then return self end
  self._running = true
  self._lastResult = nil
  self._lastErrorAlert = -math.huge
  self._clients = {}
  for i, srv in ipairs(self.servers) do self._clients[i] = Client.new({url = srv.url}) end
  self._capture = self._capture or Capture.new({log = function(msg) self.logger.i(msg) end})
  self._autoCheck = AutoCheck.new({
    segmenter = Segmenter.new({abbreviations = self.abbreviations, minWords = self.minWords, maxBuffer = self.maxBuffer}),
    isAllowed = function(app) return self.apps[app:bundleID() or ""] ~= nil end,
    onSentence = function(sentence) self:_onSentence(sentence) end,
    pauseSeconds = self.pauseSeconds,
  })
  self._menu = hs.menubar.new()
  self._menu:setClickCallback(function() self:toggleAuto() end)
  for _, hk in pairs(self._hotkeys) do hk:enable() end
  self:setAuto(hs.settings.get(self.settingsKey) == true)
  self:_checkServers()
  return self
end

--- Concise:stop()
--- Method
--- Stops auto-check, disables the hotkeys and removes the menu bar item. start() can be called again later.
function obj:stop()
  if not self._running then return self end
  self._running = false
  self._autoCheck:stop()
  self._autoCheck = nil
  for _, hk in pairs(self._hotkeys) do hk:disable() end
  self._menu:delete()
  self._menu = nil
  return self
end

--- Concise:setAuto(on)
--- Method
--- Turns auto-check on or off and remembers the choice across restarts.
function obj:setAuto(on)
  if not self._running then return self end
  hs.settings.set(self.settingsKey, on)
  if on then self._autoCheck:start() else self._autoCheck:stop() end
  self:_updateMenu()
  return self
end

function obj:toggleAuto()
  if not self._running then return end
  self:setAuto(not self._autoCheck:isRunning())
  hs.alert.show("concise auto-check " .. (self._autoCheck:isRunning() and "ON" or "OFF"))
end

--- Concise:scoreSelection()
--- Method
--- Copies the selected text (restoring the clipboard afterwards) and shows its score.
function obj:scoreSelection()
  self._capture:selection(function(text, reason)
    if not self._running then return end
    if reason == "concealed" then
      hs.alert.show("Clipboard holds a password; not touching it")
    elseif reason == "empty" then
      hs.alert.show("Select a sentence first")
    elseif text then
      self:_scoreAll(text, false)
    end
  end)
end

function obj:_onSentence(sentence)
  self.logger.i(string.format("auto: sentence len=%d", #sentence))
  if self.showSentences then
    hs.alert.show('"' .. sentence .. '"', 2)
    return
  end
  self:_scoreAll(sentence, true)
end

-- Scores text on every server and reports once all have answered, in the order of obj.servers.
function obj:_scoreAll(text, auto)
  local outcomes, remaining = {}, #self._clients
  for i, client in ipairs(self._clients) do
    client:score(text, function(err, result)
      outcomes[i] = {err = err, result = result}
      remaining = remaining - 1
      if remaining == 0 and self._running then self:_report(outcomes, auto) end
    end)
  end
end

function obj:_report(outcomes, auto)
  local multi = #outcomes > 1
  -- Auto-check alerts about errors at most once per interval, so a down server doesn't alert on every sentence.
  local showErrors = not auto or os.time() - self._lastErrorAlert >= self.errorAlertInterval
  local compact, failed = {}, false
  for i, o in ipairs(outcomes) do
    local label = multi and ((self.servers[i].name or self.servers[i].url) .. ": ") or ""
    if o.result then
      hs.alert.show(label .. formatResult(o.result), 2)
      compact[i] = formatCompact(o.result)
    else
      failed = true
      self.logger.w(string.format("score failed: %s %s", o.err.kind, tostring(o.err.status)))
      if showErrors then hs.alert.show(label .. o.err.message, 2) end
      compact[i] = "?"
    end
  end
  if auto and failed and showErrors then self._lastErrorAlert = os.time() end
  if auto then
    self._lastResult = table.concat(compact, " ")
    self:_updateMenu()
  end
end

-- Logs whether each server answers the v1 health check; a server that is not up yet is not an error.
function obj:_checkServers()
  for i, client in ipairs(self._clients) do
    client:health(function(err, info)
      if info then
        self.logger.i(string.format("%s: api %s, backend %s", self.servers[i].url, tostring(info.api), tostring(info.backend)))
      else
        self.logger.w(string.format("%s: health check failed: %s", self.servers[i].url, err.message))
      end
    end)
  end
end

function obj:_updateMenu()
  if not self._menu then return end
  local on = self._autoCheck:isRunning()
  local title = on and "ON" or "OFF"
  if on and self._lastResult then title = title .. " " .. self._lastResult end
  self._menu:setTitle(title)

  local names = {}
  for _, name in pairs(self.apps) do names[#names + 1] = name end
  table.sort(names)
  local tooltip = "Concise auto-check in " .. table.concat(names, " and ")
  local key = describeHotkey(self._hotkeySpecs.toggleAuto)
  if key then tooltip = tooltip .. " (" .. key .. ")" end
  self._menu:setTooltip(tooltip)
end

return obj
