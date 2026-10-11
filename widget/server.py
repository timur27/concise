import argparse
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import laya

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_BYTES = 10_000


def parse_args():
    p = argparse.ArgumentParser(description="Score sentences for conciseness over local HTTP.")
    p.add_argument("--model", default=os.environ.get("CONCISE_MODEL", os.path.join(ROOT, "tuning", "model")),
                   help="fine-tuned model directory (env CONCISE_MODEL)")
    p.add_argument("--base", action="store_true", help="use the untrained English Laya model instead")
    p.add_argument("--questions", default=os.path.join(ROOT, "concise.json"), help="question file the model answers")
    p.add_argument("--threshold", type=float, default=float(os.environ.get("CONCISE_THRESHOLD", "0.5")),
                   help="score at or above which a sentence counts as concise (env CONCISE_THRESHOLD)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    return p.parse_args()


def load_scorer(opts, questions):
    if opts.base:
        router = laya.Router()
        predict = lambda state: router.predict(state, questions, model="english")
    else:
        if not os.path.isdir(opts.model):
            sys.exit(f"Model directory not found: {opts.model} (set --model or CONCISE_MODEL, or use --base)")
        agent = laya.load(opts.model)
        predict = lambda state: agent.predict(state, questions)
    # The text must be wrapped as {"request": ...}; a bare string scores differently.
    score = lambda text: predict({"request": text})["answers"]["concise"]["noul"]
    score("warm up")
    return score


def make_handler(score, threshold):
    class Handler(BaseHTTPRequestHandler):
        # The server is single-threaded, so a client that stalls mid-request must not block it forever.
        timeout = 10

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                length = -1
            if length < 0:
                return self.reply(400, {"error": "bad Content-Length"})
            if length > MAX_BYTES:
                return self.reply(413, {"error": f"text longer than {MAX_BYTES} bytes"})
            text = self.rfile.read(length).decode("utf-8", errors="replace").strip()
            if not text:
                return self.reply(400, {"error": "empty text"})
            start = time.time()
            try:
                s = score(text)
            except Exception as e:
                print(f"predict failed: {e!r}", file=sys.stderr, flush=True)
                return self.reply(500, {"error": "prediction failed"})
            self.reply(200, {"score": s, "good": s >= threshold, "ms": round((time.time() - start) * 1000)})

        def reply(self, code, payload):
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


def main():
    opts = parse_args()
    try:
        with open(opts.questions, encoding="utf-8") as f:
            questions = json.load(f)
    except (OSError, ValueError) as e:
        sys.exit(f"Cannot read questions file {opts.questions}: {e}")
    score = load_scorer(opts, questions)
    try:
        server = HTTPServer((opts.host, opts.port), make_handler(score, opts.threshold))
    except OSError as e:
        sys.exit(f"Cannot listen on {opts.host}:{opts.port}: {e.strerror or e}")
    print(f"concise server on http://{opts.host}:{opts.port} ({'base' if opts.base else opts.model})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
