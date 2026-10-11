# concise

A macOS helper that scores whether a sentence is concise, short and written in plain English.
It runs locally: a small Python server answers one yes/no question with [Laya](https://github.com/NandhaKishorM/laya),
fine-tuned on your own good/bad labels, and a [Hammerspoon](https://www.hammerspoon.org/) script sends it sentences.

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
Without `--model` it loads `$CONCISE_MODEL`, or `tuning/model` in the repo.
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

## Train your own model
Label data lives outside the repo. `labeling/label.py` builds it:

```bash
python3 labeling/label.py data/sentences.txt   # g good, b bad, s unsure, u undo, q quit; --unsure to revisit
```

This writes `data/sentences.labels.csv` (`line,label`, lines numbered from 1, blank lines skipped).
An optional `data/sentences.intent.csv` with `line,pair_id` keeps paired sentences on the same side of the split.

Run the rest from a working directory; outputs (`split.json`, `laya_base/`, `train_items.pt`, `model/`,
`test_scores.json`) are written there. Running from `tuning/` lets the server find `tuning/model` without `--model`.
Training reuses the fine-tuning loop from a checkout of the Laya repository.
`--data` and `--laya-repo` can also be set with `CONCISE_DATA` and `LAYA_REPO`.

```bash
git clone https://github.com/NandhaKishorM/laya ~/code/laya
.venv/bin/python tuning/split.py --data data/                         # split.json: test set of 85+, unsure excluded
.venv/bin/python tuning/evaluate.py --base                            # baseline
.venv/bin/python tuning/train.py --laya-repo ~/code/laya --out model  # downloads the base model (~2 GB) on first run
.venv/bin/python tuning/evaluate.py model                             # AUC and accuracy, writes test_scores.json
```

`concise.json` holds the question the model answers. Retrain if you reword it.

## License
MIT
