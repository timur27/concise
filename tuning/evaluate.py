"""Report AUC and accuracy of a model on the train and test splits."""
import argparse
import json
import os

import laya

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("model", nargs="?", help="fine-tuned model directory")
parser.add_argument("--base", action="store_true", help="evaluate the untrained English Laya model instead")
parser.add_argument("--split", default="split.json", help="split file written by split.py")
parser.add_argument("--out", default="test_scores.json", help="where to write per-sentence test scores")
opts = parser.parse_args()
if bool(opts.model) == opts.base:
    parser.error("give either a model directory or --base")
if opts.model and not os.path.isdir(opts.model):
    parser.error(f"model directory not found: {opts.model}")
if not os.path.exists(opts.split):
    parser.error(f"split file not found: {opts.split} (run split.py first)")

with open(opts.split, encoding="utf-8") as f:
    split = json.load(f)
with open(os.path.join(ROOT, "concise.json"), encoding="utf-8") as f:
    question = {"concise": json.load(f)["concise"]}

if opts.base:
    router = laya.Router()
    predict = lambda state: router.predict(state, question, model="english")
else:
    agent = laya.load(opts.model)
    predict = lambda state: agent.predict(state, question)


def score(t):
    return predict({"request": t})["answers"]["concise"]["noul"]


def auc(pos, neg):
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


for name in ("train", "test"):
    rows = [dict(r, s=score(r["sentence"])) for r in split[name]]
    pos = [r["s"] for r in rows if r["label"] == "good"]
    neg = [r["s"] for r in rows if r["label"] == "bad"]
    acc = lambda t: sum((r["s"] >= t) == (r["label"] == "good") for r in rows) / len(rows)
    best = max(sorted({r["s"] for r in rows}), key=acc)
    print("%-5s n=%d  AUC=%.3f  acc@0.5=%.3f  best-threshold=%.3f acc=%.3f  mean good=%.3f bad=%.3f"
          % (name, len(rows), auc(pos, neg), acc(0.5), best, acc(best), sum(pos) / len(pos), sum(neg) / len(neg)))
    if name == "test":
        with open(opts.out, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=1, ensure_ascii=False)
