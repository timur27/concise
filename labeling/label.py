#!/usr/bin/env python3
"""Label sentences one at a time.

Keys: g = good, b = bad, s = unsure, u = undo, q = quit.
Labels are saved after every key to <sentences>.labels.csv, so you can quit and resume.
Run with --unsure to revisit only the sentences you marked unsure.
Line numbers count non-blank lines of the sentences file, starting at 1.
"""
import argparse
import csv
import os
import sys
import termios
import tty

HERE = os.path.dirname(os.path.abspath(__file__))
KEYS = {"g": "good", "b": "bad", "s": "unsure"}


def getch():
    ch = sys.stdin.read(1)
    # Skip escape sequences, so the down arrow ("\x1b[B") is not read as "b".
    if ch == "\x1b":
        ch = sys.stdin.read(1)
        if ch == "[":
            ch = sys.stdin.read(1)
            while ch and not "@" <= ch <= "~":
                ch = sys.stdin.read(1)
        elif ch == "O":
            sys.stdin.read(1)
        return "\x1b"
    return ch.lower()


def load_labels(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return [(int(r["line"]), r["label"]) for r in csv.DictReader(f)]


def save_labels(path, entries):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["line", "label"])
        w.writerows(entries)
    os.replace(tmp, path)


def main(sentences_path, redo_unsure):
    labels_path = os.path.splitext(sentences_path)[0] + ".labels.csv"

    with open(sentences_path, encoding="utf-8") as f:
        sentences = [ln.rstrip("\n") for ln in f if ln.strip()]
    total = len(sentences)

    # Entries are kept in the order they were made, so undo removes the latest one.
    entries = load_labels(labels_path)

    def current():
        return dict(entries)

    def queue():
        done = current()
        if redo_unsure:
            return [n for n in range(1, total + 1) if done.get(n) == "unsure"]
        return [n for n in range(1, total + 1) if n not in done]

    history = []
    message = ""
    while True:
        todo = queue()
        done = current()
        firm = sum(1 for v in done.values() if v != "unsure")
        unsure = len(done) - firm
        if not todo:
            print(f"\nAll done: {firm} labeled, {unsure} unsure. Saved to {labels_path}")
            if unsure and not redo_unsure:
                print(f"Run with --unsure to revisit the {unsure} unsure ones.")
            return
        n = todo[0]
        sys.stdout.write("\033[2J\033[H")
        mode = "   [revisiting unsure]" if redo_unsure else ""
        print(f"{len(done)}/{total} done, {unsure} unsure{mode}   line {n}\n")
        print(f"    {sentences[n - 1]}\n")
        print("g good   b bad   s unsure   u undo   q quit")
        if message:
            print(f"\n{message}")
        message = ""

        ch = getch()
        if ch in KEYS:
            history.append((n, done.get(n)))
            entries[:] = [e for e in entries if e[0] != n]
            entries.append((n, KEYS[ch]))
            save_labels(labels_path, entries)
        elif ch == "u":
            if entries:
                line, label = entries.pop()
                # Undoing a relabel in --unsure mode puts the old "unsure" back.
                if history and history[-1][0] == line:
                    _, previous = history.pop()
                    if previous:
                        entries.append((line, previous))
                save_labels(labels_path, entries)
                message = f"Undid line {line} ({label})."
            else:
                message = "Nothing to undo."
        elif ch == "q" or not ch:
            print(f"\nSaved {len(done)} labels to {labels_path}. Run again to resume.")
            return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sentences", nargs="?", default=os.path.join(HERE, "sentences.txt"),
                        help="text file with one sentence per line")
    parser.add_argument("--unsure", action="store_true", help="revisit only sentences marked unsure")
    opts = parser.parse_args()
    if not os.path.exists(opts.sentences):
        sys.exit(f"Sentences file not found: {opts.sentences}")
    if not sys.stdin.isatty():
        sys.exit("label.py reads single keys and needs an interactive terminal.")
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        # cbreak for the whole session: keys typed during a redraw are kept, not flushed.
        tty.setcbreak(fd, termios.TCSANOW)
        main(opts.sentences, opts.unsure)
    except KeyboardInterrupt:
        print("\nStopped. Labels so far are saved.")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
