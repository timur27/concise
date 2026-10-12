# concise

> [!WARNING]
> This is a personal experiment, not production-ready software. Expect rough edges and breaking changes, and use it at your own risk.

A macOS helper that scores whether a sentence is concise, short and written in plain English.
It runs locally: a small Python server answers one yes/no question with [Laya](https://github.com/NandhaKishorM/laya),
optionally fine-tuned on your own labels, and a [Hammerspoon](https://www.hammerspoon.org/) script sends it sentences.

Nothing leaves your machine except the one-time model download.

## Requirements
- macOS with Hammerspoon
- Python 3.10+

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## Run the widget
```bash
.venv/bin/python widget/server.py --model path/to/model
.venv/bin/python widget/server.py --base                  # untrained English model, no fine-tuning needed
```
Without `--model` it loads `$CONCISE_MODEL`.
Options: `--threshold` (default 0.5, env `CONCISE_THRESHOLD`), `--questions` (default `concise.json`), `--host`,
`--port` (default 8765; if you change it, also change `SERVER_URL` at the top of `widget/init.lua`).

Check it:
```bash
curl -s -X POST --data "You could be fast." http://127.0.0.1:8765
# {"score": 0.1842, "good": false, "ms": 21}
```

Load the Hammerspoon script from `~/.hammerspoon/init.lua`:
```lua
dofile("/path/to/concise/widget/init.lua")
```

| Key | Action |
|---|---|
| Ctrl+Option+C | score the selected text |
| Ctrl+Option+K or menu bar item | toggle auto-check: score each sentence as you finish typing it in VS Code or Notes |

Auto-check only listens while an app in `AUTO_APPS` (top of `widget/init.lua`) is in front; by default that is
VS Code and Notes. This includes VS Code's integrated terminal, so password prompts typed there can reach the buffer.
It keeps a keystroke buffer in memory only. It is cleared on Enter, Tab, Esc, arrows, Option+Backspace, clicks,
Cmd/Ctrl shortcuts and app switches, and is never written to disk. The score is the model's probability of "concise", not a measurement.
It is meant for single sentences, not paragraphs.

## Question
`concise.json` holds the question the model answers. A fine-tuned model must be retrained if you reword it.

## License
MIT
