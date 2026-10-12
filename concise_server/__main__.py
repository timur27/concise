import os
import signal
import sys
import threading
from http.server import HTTPServer

from .api import Api, make_handler
from .config import ConfigError, load_settings
from .scoring import LayaScorer, ScoringError, load_question


def main(argv=None, env=os.environ) -> int:
    try:
        settings = load_settings(sys.argv[1:] if argv is None else argv, env)
        question = load_question(settings.questions_path)
    except ConfigError as e:
        print(f"concise server: {e}", file=sys.stderr)
        return 2

    # Bind before loading the model, so a busy port fails at once instead of after a slow load.
    try:
        server = HTTPServer((settings.host, settings.port), None)
    except OSError as e:
        print(f"concise server: cannot listen on {settings.host}:{settings.port}: {e.strerror or e}", file=sys.stderr)
        return 1

    try:
        if settings.model_dir is None:
            scorer = LayaScorer.base(question)
        else:
            scorer = LayaScorer.from_model_dir(settings.model_dir, question)
    except Exception as e:
        server.server_close()
        print(f"concise server: cannot load model: {e!r}", file=sys.stderr)
        return 1
    try:
        scorer.score("warm up")
    except ScoringError as e:
        server.server_close()
        print(f"concise server: model check failed: {e}", file=sys.stderr)
        return 1

    server.RequestHandlerClass = make_handler(Api(scorer, settings.threshold, settings.max_bytes, settings.backend))
    # shutdown() blocks until serve_forever returns, so it must run off the serving thread.
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    host, port = server.server_address[:2]
    print(f"concise server on http://{host}:{port} ({settings.model_dir or 'base'})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
