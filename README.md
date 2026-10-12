# plainly

> [!WARNING]
> This is a personal experiment, not production-ready software. Expect rough edges and breaking changes, and use it at your own risk.

A macOS helper that scores whether a sentence is plain: concise, short and written in plain English.
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
.venv/bin/python -m plainly_server --model path/to/model
.venv/bin/python -m plainly_server --base                  # Laya's English model, downloaded on first run
```
Without `--model` it loads `$PLAINLY_MODEL`.
Options: `--threshold` (default 0.5, env `PLAINLY_THRESHOLD`), `--questions` (default `concise.json`), `--host`,
`--port` (default 8765). `widget/server.py` still works as an alias for `python -m plainly_server`.

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
ln -s "$PWD/Plainly.spoon" ~/.hammerspoon/Spoons/Plainly.spoon
```
```lua
hs.loadSpoon("Plainly")
-- Optional settings, before start():
-- spoon.Plainly.servers = {{name = "Base", url = "http://127.0.0.1:8765"}, {name = "Tuned", url = "http://127.0.0.1:8766"}}
-- spoon.Plainly.apps["com.apple.TextEdit"] = "TextEdit"
spoon.Plainly:bindHotkeys(spoon.Plainly.defaultHotkeys)
spoon.Plainly:start()
```
`spoon.Plainly:stop()` removes the menu bar item, disables the hotkeys and stops auto-check.
The other settings (pause length, minimum words, abbreviations) are documented at the top of `Plainly.spoon/init.lua`.

| Key | Action |
|---|---|
| Ctrl+Option+C | score the selected text |
| Ctrl+Option+K or menu bar item | toggle auto-check: score each sentence as you finish typing it in VS Code or Notes |

Auto-check only listens while an app in `spoon.Plainly.apps` is in front; by default that is
VS Code and Notes. This includes VS Code's integrated terminal, so password prompts typed there can reach the buffer.
It keeps a keystroke buffer in memory only. It is cleared on Enter, Tab, Esc, arrows, Option+Backspace, clicks,
Cmd/Ctrl shortcuts and app switches, and is never written to disk. The score is the model's probability of "concise", not a measurement.
It is meant for single sentences, not paragraphs.

## Question
`concise.json` holds the one question the model answers. The server reads the question's key and answer type from it.
The file and its `concise` key keep their pre-rename names because the fine-tuned model was trained on that exact question.

## Renamed from concise
This project was called `concise`. The old `CONCISE_MODEL` and `CONCISE_THRESHOLD` variables still work, and the
Spoon reads the old saved auto-check state once. Re-link the Spoon as `Plainly.spoon` and change `spoon.Concise` to
`spoon.Plainly` in `~/.hammerspoon/init.lua`.

## Tests
Neither suite needs Laya, Hammerspoon or a running server.
```bash
python3 -m unittest discover -s tests
lua tests/spoon_test.lua
```

## License
MIT
