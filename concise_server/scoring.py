import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from .config import ConfigError


@dataclass(frozen=True)
class Question:
    key: str
    answer_type: str
    spec: dict  # the full question file, passed to the model as-is


def load_question(path: Path) -> Question:
    try:
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ConfigError(f"cannot read questions file {path}: {e}") from None
    if not isinstance(spec, dict) or len(spec) != 1:
        raise ConfigError(f"questions file {path} must hold exactly one question")
    (key, entry), = spec.items()
    if not isinstance(entry, dict) or not isinstance(entry.get("type"), str):
        raise ConfigError(f"question {key!r} in {path} has no \"type\"")
    return Question(key=key, answer_type=entry["type"], spec=spec)


class ScoringError(Exception):
    """The model failed or answered in an unexpected shape."""


class Scorer(Protocol):
    def score(self, text: str) -> float:
        """Return a score in [0, 1], or raise ScoringError."""


Predict = Callable[[dict, dict], dict]


class LayaScorer:
    def __init__(self, predict: Predict, question: Question):
        self._predict = predict
        self._question = question

    @classmethod
    def from_model_dir(cls, path: Path, question: Question) -> "LayaScorer":
        import laya
        agent = laya.load(str(path))
        return cls(agent.predict, question)

    @classmethod
    def base(cls, question: Question) -> "LayaScorer":
        import laya
        router = laya.Router()
        return cls(lambda state, questions: router.predict(state, questions, model="english"), question)

    def score(self, text: str) -> float:
        q = self._question
        try:
            # The text must be wrapped as {"request": ...}; a bare string scores differently.
            reply = self._predict({"request": text}, q.spec)
        except Exception as e:
            raise ScoringError(f"predict failed: {type(e).__name__}") from e
        value = _dig(reply, "answers", q.key, q.answer_type)
        try:
            s = float(value)
        except (TypeError, ValueError):
            raise ScoringError(f"answers.{q.key}.{q.answer_type} is {type(value).__name__}, not a number") from None
        if not (math.isfinite(s) and 0.0 <= s <= 1.0):
            raise ScoringError(f"answers.{q.key}.{q.answer_type} is {s}, outside 0..1")
        return s


def _dig(reply: Any, *keys: str) -> Any:
    node = reply
    for i, k in enumerate(keys):
        if not isinstance(node, dict) or k not in node:
            raise ScoringError(f"model reply has no {'.'.join(keys[:i + 1])}")
        node = node[k]
    return node
