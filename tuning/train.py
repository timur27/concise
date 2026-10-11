"""Fine-tune Laya on the train split, using the training loop from the Laya repository."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import torch
from transformers import AutoTokenizer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--laya-repo", default=os.environ.get("LAYA_REPO"), required="LAYA_REPO" not in os.environ,
                    help="checkout of https://github.com/NandhaKishorM/laya (env LAYA_REPO)")
parser.add_argument("--split", default="split.json", help="split file written by split.py")
parser.add_argument("--base-dir", default="./laya_base", help="base model directory; downloaded if missing")
parser.add_argument("--items", default="train_items.pt", help="where to cache the tokenized training items")
parser.add_argument("--out", default="./model", help="where to save the fine-tuned model")
parser.add_argument("--epochs", type=int, default=5)
parser.add_argument("--limit", type=int, default=0, help="train on only the first N sentences (for smoke tests)")
parser.add_argument("--smooth", type=float, default=0.95, help="soft target for good sentences (bad get 1 - smooth)")
parser.add_argument("--micro-batch", type=int, default=8)
parser.add_argument("--grad-accum", type=int, default=2)
opts = parser.parse_args()

notebooks = os.path.join(os.path.expanduser(opts.laya_repo), "notebooks")
if not os.path.exists(os.path.join(notebooks, "laya_finetune_typed_decisions_mps.py")):
    sys.exit(f"laya_finetune_typed_decisions_mps.py not found in {notebooks}")
sys.path.insert(0, notebooks)
import laya_finetune_typed_decisions_mps as ft  # noqa: E402

with open(opts.split, encoding="utf-8") as f:
    split = json.load(f)["train"]
if opts.limit:
    split = split[:opts.limit]

with open(os.path.join(ROOT, "concise.json"), encoding="utf-8") as f:
    question = json.load(f)["concise"]
model_dir = ft.prepare_model(opts.base_dir)
with open(Path(model_dir) / "rl_agent_config.json", encoding="utf-8") as f:
    cfg = json.load(f)
tokenizer = AutoTokenizer.from_pretrained(Path(model_dir) / "tokenizer")

items = []
for row in split:
    p = opts.smooth if row["label"] == "good" else 1.0 - opts.smooth
    gold = {"probabilities": {"true": p, "false": 1.0 - p}}
    item = ft.build_training_item(tokenizer, cfg, {"request": row["sentence"]}, question, gold)
    if item is not None:
        items.append(item)
print("items:", len(items), "of", len(split))
torch.save(items, opts.items)

args = argparse.Namespace(
    epochs=opts.epochs, micro_batch=opts.micro_batch, grad_accum=opts.grad_accum,
    calib_max=400, no_checkpointing=False, output_dir=opts.out,
)
start = time.time()
ft.train(args, model_dir, opts.items, ft.choose_device("auto"))
print("training seconds: %.0f" % (time.time() - start))
