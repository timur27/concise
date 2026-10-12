-- Watches keystrokes in allowed apps and reports each finished sentence.
-- Privacy: the event taps run only while started and an allowed app is in front, so other apps' keys never reach us.
-- The buffer lives in memory only and is cleared on navigation keys, shortcuts, clicks and app switches.
local AutoCheck = {}
AutoCheck.__index = AutoCheck

local CLEAR_KEY_NAMES = {"tab", "escape", "left", "right", "up", "down", "home", "end",
  "pageup", "pagedown", "forwarddelete"}

-- Builds the key-code table classify needs from a name->code map such as hs.keycodes.map.
function AutoCheck.keyCodes(map)
  local clear = {}
  for _, name in ipairs(CLEAR_KEY_NAMES) do clear[map[name]] = true end
  return {clear = clear, enter = {[map["return"]] = true, [map["padenter"]] = true}, backspace = map["delete"]}
end

-- Turns a key-down event into a buffer action: "reset", "enter", "backspace", "text" (with the typed text) or nil.
function AutoCheck.classify(flags, keyCode, chars, codes)
  -- Option+Backspace deletes a whole word, which the buffer can't mirror.
  if flags.cmd or flags.ctrl or codes.clear[keyCode] or (flags.alt and keyCode == codes.backspace) then
    return "reset"
  elseif codes.enter[keyCode] then
    return "enter"
  elseif keyCode == codes.backspace then
    return "backspace"
  elseif chars and chars ~= "" then
    return "text", chars
  end
  return nil
end

-- opts: segmenter, isAllowed(app) -> bool, onSentence(sentence), pauseSeconds
function AutoCheck.new(opts)
  local self = setmetatable({
    segmenter = opts.segmenter,
    isAllowed = opts.isAllowed,
    onSentence = opts.onSentence,
    codes = AutoCheck.keyCodes(hs.keycodes.map),
    running = false,
    inAllowedApp = false,
  }, AutoCheck)
  self.pauseTimer = hs.timer.delayed.new(opts.pauseSeconds or 1.5, function() self:_emit(self.segmenter:pauseElapsed()) end)
  self.keyTap = hs.eventtap.new({hs.eventtap.event.types.keyDown}, function(e) self:_onKey(e); return false end)
  self.mouseTap = hs.eventtap.new({hs.eventtap.event.types.leftMouseDown}, function() self:_clear(); return false end)
  self.appWatcher = hs.application.watcher.new(function(_, event, app)
    if event == hs.application.watcher.activated then
      self:_clear()
      self:_syncTaps(app)
    end
  end)
  return self
end

function AutoCheck:_emit(sentence)
  if sentence then self.onSentence(sentence) end
end

function AutoCheck:_clear()
  self.segmenter:reset()
  self.pauseTimer:stop()
end

function AutoCheck:_syncTaps(app)
  self.inAllowedApp = self.running and app ~= nil and self.isAllowed(app)
  if self.inAllowedApp then
    self.keyTap:start()
    self.mouseTap:start()
  else
    self.keyTap:stop()
    self.mouseTap:stop()
  end
end

function AutoCheck:_onKey(e)
  if not self.inAllowedApp then return end
  local seg = self.segmenter
  local wasPending = seg:isPending()
  local action, text = AutoCheck.classify(e:getFlags(), e:getKeyCode(), e:getCharacters(), self.codes)
  if action == "reset" then
    seg:reset()
  elseif action == "enter" then
    self:_emit(seg:enter())
  elseif action == "backspace" then
    seg:backspace()
  elseif action == "text" then
    for c in text:gmatch(utf8.charpattern) do self:_emit(seg:feed(c)) end
  end
  -- The pause countdown starts when an end mark is typed and keeps running through closing quotes.
  if not seg:isPending() then
    self.pauseTimer:stop()
  elseif not wasPending then
    self.pauseTimer:start()
  end
end

function AutoCheck:start()
  if self.running then return end
  self.running = true
  self:_clear()
  self.appWatcher:start()
  self:_syncTaps(hs.application.frontmostApplication())
end

function AutoCheck:stop()
  self.running = false
  self.appWatcher:stop()
  self:_syncTaps(nil)
  self:_clear()
end

function AutoCheck:isRunning()
  return self.running
end

return AutoCheck
