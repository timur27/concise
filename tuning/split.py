"""Split labeled sentences into train and test sets, keeping paired sentences on the same side."""
import argparse
import csv
import json
import os
import random

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--data", default=os.environ.get("CONCISE_DATA"), required="CONCISE_DATA" not in os.environ,
                    help="directory with sentences.txt, sentences.labels.csv and optionally sentences.intent.csv "
                         "(env CONCISE_DATA)")
parser.add_argument("--test-size", type=int, default=85, help="minimum number of test sentences")
parser.add_argument("--seed", type=int, default=7, help="shuffle seed")
parser.add_argument("--out", default="split.json", help="output file")
opts = parser.parse_args()


def path(name):
    return os.path.join(opts.data, name)


# Same numbering as labeling/label.py: non-blank lines, starting at 1.
with open(path("sentences.txt"), encoding="utf-8") as f:
    sents = [ln.rstrip("\n") for ln in f if ln.strip()]
with open(path("sentences.labels.csv"), encoding="utf-8", newline="") as f:
    labels = {int(r["line"]): r["label"] for r in csv.DictReader(f)}
pair = {}
if os.path.exists(path("sentences.intent.csv")):
    with open(path("sentences.intent.csv"), encoding="utf-8", newline="") as f:
        pair = {int(r["line"]): r["pair_id"] for r in csv.DictReader(f)}

missing = sorted(n for n in labels if not 1 <= n <= len(sents))
if missing:
    raise SystemExit("sentences.labels.csv has lines %s that are not in sentences.txt (%d sentences)"
                     % (missing[:5], len(sents)))

units = {}
for n, lab in labels.items():
    if lab == "unsure":
        continue
    units.setdefault(pair.get(n) or "solo-%d" % n, []).append(n)

keys = sorted(units)
random.Random(opts.seed).shuffle(keys)
test, train = [], []
for k in keys:
    (test if len(test) < opts.test_size else train).extend(units[k])


def rows(ns):
    return [{"line": n, "sentence": sents[n - 1], "label": labels[n]} for n in sorted(ns)]


with open(opts.out, "w", encoding="utf-8") as f:
    json.dump({"train": rows(train), "test": rows(test)}, f, indent=1, ensure_ascii=False)
for name, ns in (("train", train), ("test", test)):
    print(name, len(ns), "good", sum(labels[n] == "good" for n in ns), "bad", sum(labels[n] == "bad" for n in ns))
