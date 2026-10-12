# concise

> [!WARNING]
> This is a personal experiment, not production-ready software. Expect rough edges and breaking changes, and use it at your own risk.

A macOS helper that scores whether a sentence is concise, short and written in plain English.
It runs locally: a small Python server answers one yes/no question with [Laya](https://github.com/NandhaKishorM/laya),
and a [Hammerspoon](https://www.hammerspoon.org/) Spoon sends it sentences.

Nothing leaves your machine except the one-time model download.

## Requirements
- macOS with Hammerspoon
- Python 3.10+

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## Run the server
```bash
.venv/bin/python -m concise_server --model path/to/model
.venv/bin/python -m concise_server --base                  # Laya's English model, downloaded on first run
```
Without `--model` it loads `$CONCISE_MODEL`.
Options: `--threshold` (default 0.5, env `CONCISE_THRESHOLD`), `--questions` (default `concise.json`), `--host`,
`--port` (default 8765). `widget/server.py` still works as an alias for `python -m concise_server`.

Check it:
```bash
curl -s -X POST --data "You could be fast." http://127.0.0.1:8765/v1/score
# {"score": 0.1438, "good": false, "threshold": 0.5, "ms": 17}
curl -s http://127.0.0.1:8765/v1/health
```
The request and response format is in [PROTOCOL.md](PROTOCOL.md).

## Load the Hammerspoon Spoon
Link the Spoon into Hammerspoon, then load it from `~/.hammerspoon/init.lua`:
```bash
ln -s "$PWD/Concise.spoon" ~/.hammerspoon/Spoons/Concise.spoon
```
```lua
hs.loadSpoon("Concise")
-- Optional settings, before start():
-- spoon.Concise.servers = {{name = "Base", url = "http://127.0.0.1:8765"}, {name = "Tuned", url = "http://127.0.0.1:8766"}}
-- spoon.Concise.apps["com.apple.TextEdit"] = "TextEdit"
spoon.Concise:bindHotkeys(spoon.Concise.defaultHotkeys)
spoon.Concise:start()
```
`spoon.Concise:stop()` removes the menu bar item, disables the hotkeys and stops auto-check.
The other settings (pause length, minimum words, abbreviations) are documented at the top of `Concise.spoon/init.lua`.

| Key | Action |
|---|---|
| Ctrl+Option+C | score the selected text |
| Ctrl+Option+K or menu bar item | toggle auto-check: score each sentence as you finish typing it in VS Code or Notes |

Auto-check only listens while an app in `spoon.Concise.apps` is in front; by default that is
VS Code and Notes. This includes VS Code's integrated terminal, so password prompts typed there can reach the buffer.
It keeps a keystroke buffer in memory only. It is cleared on Enter, Tab, Esc, arrows, Option+Backspace, clicks,
Cmd/Ctrl shortcuts and app switches, and is never written to disk. The score is the model's probability of "concise", not a measurement.
It is meant for single sentences, not paragraphs.

## Question
`concise.json` holds the one question the model answers. The server reads the question's key and answer type from it.

## Tests
Neither suite needs Laya, Hammerspoon or a running server.
```bash
python3 -m unittest discover -s tests
lua tests/spoon_test.lua
```

## License
MIT
