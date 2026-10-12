import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path
from unittest import mock

from plainly_server import __main__ as entry
from plainly_server.api import Api, make_handler
from plainly_server.config import ROOT, ConfigError, load_settings
from plainly_server.scoring import LayaScorer, Question, ScoringError, load_question

QUESTION = Question(key="concise", answer_type="noul", spec={"concise": {"type": "noul", "instructions": "?"}})


class FakeScorer:
    def __init__(self, result=0.7):
        self.result = result
        self.seen = []

    def score(self, text):
        self.seen.append(text)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def api(result=0.7, max_bytes=100):
    ticks = iter([1.0, 1.021])
    return Api(FakeScorer(result), threshold=0.5, max_bytes=max_bytes, backend="base", clock=lambda: next(ticks))


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.model = tempfile.mkdtemp()

    def test_flag_beats_bad_env_threshold(self):
        s = load_settings(["--base", "--threshold", "0.6"], {"PLAINLY_THRESHOLD": "abc"})
        self.assertEqual(s.threshold, 0.6)

    def test_bad_env_threshold_is_a_config_error(self):
        with self.assertRaisesRegex(ConfigError, "number"):
            load_settings(["--base"], {"PLAINLY_THRESHOLD": "abc"})

    def test_threshold_out_of_range(self):
        with self.assertRaisesRegex(ConfigError, "between 0 and 1"):
            load_settings(["--base", "--threshold", "2"], {})

    def test_base_and_model_are_exclusive(self):
        with self.assertRaises(ConfigError):
            load_settings(["--base", "--model", self.model], {})

    def test_model_from_env(self):
        s = load_settings([], {"PLAINLY_MODEL": self.model})
        self.assertEqual(s.model_dir, Path(self.model))
        self.assertEqual(s.backend, "model")

    def test_pre_rename_env_still_works(self):
        s = load_settings([], {"CONCISE_MODEL": self.model, "CONCISE_THRESHOLD": "0.7"})
        self.assertEqual((s.model_dir, s.threshold), (Path(self.model), 0.7))

    def test_new_env_beats_pre_rename_env(self):
        s = load_settings(["--base"], {"PLAINLY_THRESHOLD": "0.6", "CONCISE_THRESHOLD": "0.7"})
        self.assertEqual(s.threshold, 0.6)

    def test_missing_model(self):
        with self.assertRaisesRegex(ConfigError, "no model"):
            load_settings([], {})
        with self.assertRaisesRegex(ConfigError, "not found"):
            load_settings(["--model", self.model + "/nope"], {})

    def test_defaults(self):
        s = load_settings(["--base"], {})
        self.assertEqual((s.host, s.port, s.threshold, s.backend), ("127.0.0.1", 8765, 0.5, "base"))
        self.assertEqual(s.questions_path, ROOT / "config" / "concise.json")


class QuestionTest(unittest.TestCase):
    def write(self, content):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_repo_question_file(self):
        q = load_question(ROOT / "config" / "concise.json")
        self.assertEqual((q.key, q.answer_type), ("concise", "noul"))

    def test_key_comes_from_file(self):
        q = load_question(self.write('{"brevity": {"type": "noul", "instructions": "?"}}'))
        self.assertEqual(q.key, "brevity")

    def test_rejects_zero_or_two_questions(self):
        for content in ["{}", '{"a": {"type": "noul"}, "b": {"type": "noul"}}', "[]", "not json"]:
            with self.subTest(content=content), self.assertRaises(ConfigError):
                load_question(self.write(content))

    def test_rejects_missing_type(self):
        with self.assertRaisesRegex(ConfigError, "type"):
            load_question(self.write('{"concise": {"instructions": "?"}}'))


class LayaScorerTest(unittest.TestCase):
    def scorer(self, reply):
        calls = []

        def predict(state, questions):
            calls.append((state, questions))
            if isinstance(reply, Exception):
                raise reply
            return reply

        return LayaScorer(predict, QUESTION), calls

    def test_wraps_text_and_extracts_score(self):
        s, calls = self.scorer({"answers": {"concise": {"noul": 0.25}}})
        self.assertEqual(s.score("Hi there."), 0.25)
        self.assertEqual(calls, [({"request": "Hi there."}, QUESTION.spec)])

    def test_accepts_numeric_scalars(self):
        class Scalar:  # stands in for a numpy float
            def __float__(self):
                return 0.5

        s, _ = self.scorer({"answers": {"concise": {"noul": Scalar()}}})
        self.assertEqual(s.score("x"), 0.5)

    def test_contract_violations_raise_scoring_error(self):
        for reply in [{}, {"answers": {}}, {"answers": {"concise": {}}}, {"answers": {"concise": {"noul": None}}},
                      {"answers": {"concise": {"noul": "high"}}}, {"answers": {"concise": {"noul": 1.5}}},
                      {"answers": {"concise": {"noul": float("nan")}}}, None]:
            with self.subTest(reply=reply), self.assertRaises(ScoringError):
                self.scorer(reply)[0].score("x")

    def test_predict_exception_hides_its_message(self):
        s, _ = self.scorer(RuntimeError("secret typed text"))
        with self.assertRaises(ScoringError) as cm:
            s.score("x")
        self.assertNotIn("secret", str(cm.exception))


class ApiTest(unittest.TestCase):
    def test_score(self):
        r = api(0.7).score("  Short sentence.  ".encode())
        self.assertEqual(r.status, 200)
        self.assertEqual(r.body, {"score": 0.7, "good": True, "threshold": 0.5, "ms": 21})

    def test_threshold_is_inclusive(self):
        self.assertTrue(api(0.5).score(b"x").body["good"])
        self.assertFalse(api(0.49).score(b"x").body["good"])

    def test_errors(self):
        cases = [(b"   ", 400, "empty_text"), (b"\xff\xfe", 400, "bad_encoding"), (b"x" * 101, 413, "too_large")]
        for body, status, code in cases:
            with self.subTest(code=code):
                r = api().score(body)
                self.assertEqual((r.status, r.body["error"]["code"]), (status, code))

    def test_scoring_error_is_500(self):
        with mock.patch("sys.stderr"):
            r = api(ScoringError("bad reply")).score(b"x")
        self.assertEqual((r.status, r.body["error"]["code"]), (500, "model_failed"))

    def test_health(self):
        self.assertEqual(api().health().body, {"status": "ok", "api": 1, "backend": "base", "max_bytes": 100})


class HttpTest(unittest.TestCase):
    def setUp(self):
        self.scorer = FakeScorer(0.2)
        a = Api(self.scorer, threshold=0.5, max_bytes=100, backend="model")
        self.server = HTTPServer(("127.0.0.1", 0), make_handler(a))
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def request(self, path, data=None):
        req = urllib.request.Request(self.url + path, data=data,
                                     headers={"Content-Type": "text/plain; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.load(resp)
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.load(e)

    def test_v1_and_legacy_score(self):
        for path in ["/v1/score", "/"]:
            with self.subTest(path=path):
                status, body = self.request(path, "Wordy text.".encode())
                self.assertEqual(status, 200)
                self.assertEqual((body["score"], body["good"]), (0.2, False))

    def test_health(self):
        self.assertEqual(self.request("/v1/health"), (200, {"status": "ok", "api": 1, "backend": "model",
                                                            "max_bytes": 100}))

    def test_too_large_is_refused_before_scoring(self):
        status, body = self.request("/v1/score", b"x" * 101)
        self.assertEqual((status, body["error"]["code"]), (413, "too_large"))
        self.assertEqual(self.scorer.seen, [])

    def test_unknown_path(self):
        self.assertEqual(self.request("/v2/score", b"x")[0], 404)
        self.assertEqual(self.request("/")[0], 404)


class MainTest(unittest.TestCase):
    def test_busy_port_fails_before_loading_the_model(self):
        busy = HTTPServer(("127.0.0.1", 0), None)
        port = str(busy.server_address[1])
        try:
            with mock.patch.object(LayaScorer, "base") as base, mock.patch("sys.stderr"):
                code = entry.main(["--base", "--port", port], {})
            self.assertEqual(code, 1)
            base.assert_not_called()
        finally:
            busy.server_close()

    def test_config_error_exits_2(self):
        with mock.patch("sys.stderr"):
            self.assertEqual(entry.main(["--base", "--threshold", "x"], {}), 2)

    def test_warm_up_contract_failure_exits_cleanly(self):
        broken = LayaScorer(lambda state, q: {"answers": {}}, QUESTION)
        with mock.patch.object(LayaScorer, "base", return_value=broken), mock.patch("sys.stderr"):
            self.assertEqual(entry.main(["--base", "--port", "0"], {}), 1)


if __name__ == "__main__":
    unittest.main()
