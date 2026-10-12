import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 8765


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    model_dir: Path | None  # None means Laya's English base model
    questions_path: Path
    threshold: float
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    max_bytes: int = 10_000

    @property
    def backend(self) -> str:
        return "base" if self.model_dir is None else "model"


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ConfigError(message)


def _parser() -> argparse.ArgumentParser:
    p = _Parser(prog="python -m concise_server", description="Score sentences for conciseness over local HTTP.")
    source = p.add_mutually_exclusive_group()
    source.add_argument("--model", help="fine-tuned model directory (env CONCISE_MODEL)")
    source.add_argument("--base", action="store_true", help="use the untrained English Laya model instead")
    p.add_argument("--questions", type=Path, default=ROOT / "concise.json", help="question file the model answers")
    p.add_argument("--threshold", help="score at or above which a sentence counts as concise (env CONCISE_THRESHOLD)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    return p


def load_settings(argv: Sequence[str], env: Mapping[str, str]) -> Settings:
    opts = _parser().parse_args(argv)

    raw = opts.threshold if opts.threshold is not None else env.get("CONCISE_THRESHOLD", "0.5")
    try:
        threshold = float(raw)
    except ValueError:
        raise ConfigError(f"threshold must be a number, got {raw!r}") from None
    if not 0.0 <= threshold <= 1.0:
        raise ConfigError(f"threshold must be between 0 and 1, got {threshold}")

    if not 0 <= opts.port <= 65535:
        raise ConfigError(f"port must be between 0 and 65535, got {opts.port}")

    model_dir = None
    if not opts.base:
        model = opts.model or env.get("CONCISE_MODEL", "")
        if not model:
            raise ConfigError("no model given (set --model or CONCISE_MODEL, or use --base)")
        model_dir = Path(model)
        if not model_dir.is_dir():
            raise ConfigError(f"model directory not found: {model_dir}")

    return Settings(model_dir=model_dir, questions_path=opts.questions, threshold=threshold,
                    host=opts.host, port=opts.port)
