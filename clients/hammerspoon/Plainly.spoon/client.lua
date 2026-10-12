-- HTTP client for the plainly server's v1 wire contract (see PROTOCOL.md).
-- Callbacks get (nil, result) or (err), where err = {kind, status, code, message} and kind is one of:
--   "unreachable" (no server), "rejected" (4xx, the text was refused), "server" (5xx), "protocol" (unexpected reply).
local Client = {}
Client.__index = Client

local HEADERS = {["Content-Type"] = "text/plain; charset=utf-8"}

function Client.new(opts)
  return setmetatable({
    url = opts.url:gsub("/+$", ""),
    http = opts.http or hs.http,
    decode = opts.decode or hs.json.decode,
  }, Client)
end

function Client:_decode(body)
  local ok, value = pcall(self.decode, body or "")
  if ok and type(value) == "table" then return value end
  return nil
end

function Client:_failure(status, body)
  if status < 0 then
    return {kind = "unreachable", status = status, message = "plainly server not running at " .. self.url}
  end
  local reply = self:_decode(body)
  local e = reply and type(reply.error) == "table" and reply.error
  if status ~= 200 and e and type(e.message) == "string" then
    return {kind = status < 500 and "rejected" or "server", status = status, code = e.code, message = e.message}
  end
  return {kind = "protocol", status = status, message = "unexpected reply from plainly server (HTTP " .. status .. ")"}
end

function Client:score(text, callback)
  self.http.asyncPost(self.url .. "/v1/score", text, HEADERS, function(status, body)
    if status == 200 then
      local r = self:_decode(body)
      if r and type(r.score) == "number" and type(r.good) == "boolean" then
        return callback(nil, {score = r.score, good = r.good, ms = r.ms})
      end
    end
    callback(self:_failure(status, body))
  end)
end

function Client:health(callback)
  self.http.asyncGet(self.url .. "/v1/health", nil, function(status, body)
    local r = status == 200 and self:_decode(body)
    if r and r.status == "ok" then return callback(nil, r) end
    callback(self:_failure(status, body))
  end)
end

return Client
