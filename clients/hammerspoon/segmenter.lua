-- Splits typed characters into finished sentences. Pure Lua with no Hammerspoon dependency:
-- the caller decodes keys and owns the pause timer (it should call pauseElapsed while isPending is true).
local Segmenter = {}
Segmenter.__index = Segmenter

local END = {["."] = true, ["?"] = true, ["!"] = true}
local CLOSERS = {['"'] = true, ["'"] = true, [")"] = true, ["]"] = true, ["”"] = true, ["’"] = true, ["»"] = true}

Segmenter.DEFAULT_ABBREVIATIONS = {"e.g.", "i.e.", "etc.", "vs.", "mr.", "mrs.", "ms.", "dr."}

function Segmenter.new(opts)
  opts = opts or {}
  local abbreviations = {}
  for _, a in ipairs(opts.abbreviations or Segmenter.DEFAULT_ABBREVIATIONS) do abbreviations[a:lower()] = true end
  return setmetatable({
    abbreviations = abbreviations,
    minWords = opts.minWords or 3,
    maxBuffer = opts.maxBuffer or 1000,
    buf = "",
    pending = false,
  }, Segmenter)
end

function Segmenter:reset()
  self.buf = ""
  self.pending = false
end

-- True while the buffer ends in an end mark that may or may not finish the sentence.
function Segmenter:isPending()
  return self.pending
end

-- Returns ended, sentence. ended is false when the end mark belonged to an abbreviation and the buffer keeps growing;
-- sentence is nil when the sentence ended but is too short to score.
function Segmenter:_confirm()
  self.pending = false
  local sentence = self.buf:match("^%s*(.-)%s*$")
  local lastWord = (sentence:match("(%S+)$") or ""):lower():gsub("^[\"'(%[“‘«]+", ""):gsub("[\"')%]”’»]+$", "")
  if self.abbreviations[lastWord] then return false end
  self.buf = ""
  local _, words = sentence:gsub("%S+", "")
  if words >= self.minWords then return true, sentence end
  return true
end

-- Feeds one character; returns the previous sentence if this character finished it.
function Segmenter:feed(c)
  if self.pending and not END[c] and not CLOSERS[c] then
    if c:match("^%s$") then
      local ended, sentence = self:_confirm()
      if ended then return sentence end
    end
    self.pending = false
  end
  self.buf = self.buf .. c
  if #self.buf > self.maxBuffer then self.buf = self.buf:sub(-self.maxBuffer) end
  if END[c] then self.pending = true end
  return nil
end

function Segmenter:backspace()
  local last = utf8.offset(self.buf, -1)
  self.buf = last and self.buf:sub(1, last - 1) or ""
  self.pending = END[self.buf:sub(-1)] or false
end

-- Enter finishes any pending sentence and starts over.
function Segmenter:enter()
  local sentence
  if self.pending then sentence = select(2, self:_confirm()) end
  self:reset()
  return sentence
end

function Segmenter:pauseElapsed()
  if not self.pending then return nil end
  return select(2, self:_confirm())
end

return Segmenter
