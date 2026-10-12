import json
import sys
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from typing import Callable

from .scoring import Scorer, ScoringError

API_VERSION = 1


@dataclass(frozen=True)
class Response:
    status: int
    body: dict

class Api:
    """Transport-neutral request handling: validation, scoring, verdict and typed errors."""

    def __init__(self, scorer: Scorer, threshold: float, max_bytes: int, backend: str,
                 clock: Callable[[], float] = time.monotonic):
        self._scorer = scorer
        self._threshold = threshold
        self.max_bytes = max_bytes
        self._backend = backend
        self._clock = clock

    def score(self, body: bytes) -> Response:
        if len(body) > self.max_bytes:
            return self.too_large()
        try:
            text = body.decode("utf-8").strip()
        except UnicodeDecodeError:
            return error(400, "bad_encoding", "body is not valid UTF-8")
        if not text:
            return error(400, "empty_text", "empty text")
        start = self._clock()
        try:
            s = self._scorer.score(text)
        except ScoringError as e:
            print(f"scoring failed: {e}", file=sys.stderr, flush=True)
            return error(500, "model_failed", "prediction failed")
        ms = round((self._clock() - start) * 1000)
        return Response(200, {"score": s, "good": s >= self._threshold, "threshold": self._threshold, "ms": ms})

    def health(self) -> Response:
        return Response(200, {"status": "ok", "api": API_VERSION, "backend": self._backend,
                              "max_bytes": self.max_bytes})

    def too_large(self) -> Response:
        return error(413, "too_large", f"text longer than {self.max_bytes} bytes")


def error(status: int, code: str, message: str) -> Response:
    return Response(status, {"error": {"code": code, "message": message}})


# "/" is the pre-v1 endpoint, kept so older clients and the README's curl example keep working.
SCORE_PATHS = {"/v1/score", "/"}
HEALTH_PATHS = {"/v1/health"}


def make_handler(api: Api) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        # The server is single-threaded, so a client that stalls mid-request must not block it forever.
        timeout = 10

        def do_POST(self):
            if self.path not in SCORE_PATHS:
                return self.send(self.not_found())
            try:
                length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                length = -1
            if length < 0:
                return self.send(error(400, "bad_request", "bad Content-Length"))
            # Refuse before reading, so an oversized body is never buffered.
            if length > api.max_bytes:
                return self.send(api.too_large())
            self.send(api.score(self.rfile.read(length)))

        def do_GET(self):
            if self.path not in HEALTH_PATHS:
                return self.send(self.not_found())
            self.send(api.health())

        def not_found(self):
            return error(404, "not_found", f"no endpoint {self.command} {self.path}")

        def send(self, r: Response):
            body = json.dumps(r.body).encode()
            self.send_response(r.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler
