"""Spec 009 T6: backend interface, retry, error sanitizing and the registry (fake backend only)."""

import io
import logging
import random
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from src.llm import backends
from src.llm.backends import base, fake
from src.llm.schema import MAX_RAW_CHARS

SENTINEL = "zq-sentinel-backend the purple lighthouse"
FAKE_KEY = "sk-test-zq-not-a-real-key-0000"


def request(n=1, text=SENTINEL):
    return base.Request(f"{n:064x}", ({"role": "system", "content": "instr"}, {"role": "user", "content": text}),
                        {"type": "object"})


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.error_log = base.ErrorLog(Path("outputs/llm/errors/test.log"), self.root)
        self.stats = base.CallStats()
        self.sleeps = []

    def tearDown(self):
        self._tmp.cleanup()

    def run_batch(self, backend, batch, **kwargs):
        return base.generate_with_retry(backend, batch, error_log=self.error_log, stats=self.stats,
                                        sleep=self.sleeps.append, rng=random.Random(7), **kwargs)


class RetryTests(Fixture):
    def test_ac_009_3b_transient_5xx_then_success_counts_one_retry(self):
        backend = fake.FakeBackend(failures=[base.TransportError("busy", status=503)])
        responses = self.run_batch(backend, [request()])
        self.assertEqual([r.finish_reason for r in responses], ["stop"])
        self.assertEqual((self.stats.retries, self.stats.transport_errors, self.stats.batches), (1, 1, 1))
        self.assertEqual(len(self.sleeps), 1)

    def test_ac_009_3b_five_failures_stop_the_run_without_a_response(self):
        backend = fake.FakeBackend(failures=[base.TransportError("down", status=502)] * 5)
        with self.assertRaisesRegex(base.RunStopped, "after 5 attempts"):
            self.run_batch(backend, [request()])
        self.assertEqual(backend.batches, [])
        self.assertEqual((self.stats.retries, self.stats.transport_errors), (4, 5))
        self.assertEqual(len(self.sleeps), 4, "no sleep after the final attempt")

    def test_rate_limits_are_counted_and_retry_after_is_honoured(self):
        backend = fake.FakeBackend(failures=[base.TransportError("slow down", status=429, retry_after=30)])
        self.run_batch(backend, [request()])
        self.assertEqual(self.stats.rate_limited, 1)
        self.assertGreaterEqual(self.sleeps[0], 30)

    def test_unmapped_exception_stops_at_once(self):
        backend = fake.FakeBackend(failures=[KeyError("boom")])
        with self.assertRaisesRegex(base.RunStopped, "unmapped"):
            self.run_batch(backend, [request()])
        self.assertEqual(self.sleeps, [])

    def test_mismatched_responses_stop_the_run(self):
        class Wrong(fake.FakeBackend):
            def generate(self, batch):
                return list(reversed(super().generate(batch)))

        with self.assertRaisesRegex(base.RunStopped, "do not match"):
            self.run_batch(Wrong(), [request(1), request(2)])

    def test_empty_batch_makes_no_call(self):
        backend = fake.FakeBackend()
        self.assertEqual(self.run_batch(backend, []), [])
        self.assertEqual(backend.batches, [])


class BackoffTests(unittest.TestCase):
    def test_schedule_matches_full_jitter_under_a_fixed_rng(self):
        rng, expected_rng = random.Random(42), random.Random(42)
        for failure, ceiling in ((1, 2), (2, 4), (3, 8), (4, 16), (5, 32), (6, 60), (9, 60)):
            with self.subTest(failure=failure):
                delay = base.backoff_delay(failure, rng)
                self.assertEqual(delay, expected_rng.uniform(0, ceiling))
                self.assertLessEqual(delay, ceiling)

    def test_retry_after_is_a_floor_and_is_capped(self):
        self.assertGreaterEqual(base.backoff_delay(1, random.Random(1), 10), 10)
        self.assertEqual(base.backoff_delay(1, random.Random(1), 10_000), base.MAX_RETRY_AFTER)
        rng_a, rng_b = random.Random(3), random.Random(3)
        self.assertEqual(base.backoff_delay(1, rng_a, -5), base.backoff_delay(1, rng_b, None))
        with self.assertRaises(ValueError):
            base.backoff_delay(0, random.Random(1))


class SanitizerTests(Fixture):
    def test_ac_009_5_echoed_sentinel_and_key_never_reach_logs_or_stderr(self):
        backend = fake.FakeBackend(failures=[fake.echoing_error(503, FAKE_KEY)] * 5)
        stderr = io.StringIO()
        with self.assertLogs("src.llm.backends.base", logging.WARNING) as logs, redirect_stderr(stderr):
            with self.assertRaises(base.RunStopped) as caught:
                self.run_batch(backend, [request()])
        shown = "\n".join(logs.output) + stderr.getvalue() + str(caught.exception)
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)
        for secret in ("zq-sentinel", "purple lighthouse", FAKE_KEY):
            self.assertNotIn(secret, shown)
        self.assertIn("status=503", shown)
        self.assertIn("request_id=req_fake01", shown)
        raw = (self.root / "outputs/llm/errors/test.log").read_text(encoding="utf-8")
        self.assertIn("zq-sentinel", raw, "the full body is kept in the git-ignored raw log")

    def test_unmapped_error_text_is_not_shown(self):
        backend = fake.FakeBackend(failures=[RuntimeError(SENTINEL + FAKE_KEY)])
        with self.assertRaises(base.RunStopped) as caught:
            self.run_batch(backend, [request()])
        self.assertNotIn("zq-sentinel", str(caught.exception))
        self.assertNotIn(FAKE_KEY, str(caught.exception))
        self.assertIn("RuntimeError", str(caught.exception))

    def test_untrusted_status_and_request_id_are_dropped(self):
        error = base.TransportError("x", status="503 " + SENTINEL, request_id="id with " + SENTINEL)
        shown = base.describe(error, "abcd")
        self.assertEqual(shown, "TransportError keys=abcd")

    def test_error_log_must_live_under_outputs(self):
        with self.assertRaises(ValueError):
            base.ErrorLog(Path("logs/errors.log"), self.root)


class ResponseTests(unittest.TestCase):
    def test_raw_is_clipped_one_past_the_parser_bound(self):
        response = base.Response("a" * 64, "x" * (MAX_RAW_CHARS + 50), "stop")
        self.assertEqual(len(response.raw), MAX_RAW_CHARS + 1)

    def test_unknown_finish_reason_and_non_string_raw_are_refused(self):
        with self.assertRaises(ValueError):
            base.Response("a" * 64, "", "eos")
        with self.assertRaises(TypeError):
            base.Response("a" * 64, None, "stop")


class RegistryTests(unittest.TestCase):
    def test_known_backend_resolves_and_unknown_is_refused(self):
        self.assertIs(backends.backend_class("fake"), fake.FakeBackend)
        with self.assertRaises(ValueError):
            backends.backend_class("local-shell")

    def test_paid_backends_are_marked(self):
        self.assertEqual(backends.PAID, {"anthropic", "openai"})
        self.assertNotIn("vllm", backends.PAID)

    def test_importing_the_core_never_imports_heavy_dependencies(self):
        code = ("import sys, src.llm, src.llm.backends, src.llm.backends.base, src.llm.cache, src.llm.inputs, "
                "src.llm.preflight, src.llm.recipe, src.llm.streams, src.llm.run; heavy = [m for m in ('vllm', 'torch', 'transformers', 'anthropic', 'openai') "
                "if m in sys.modules]; print(heavy)")
        result = subprocess.run([sys.executable, "-E", "-s", "-c", code], capture_output=True, text=True,
                                cwd=Path(__file__).resolve().parents[1], check=True)
        self.assertEqual(result.stdout.strip(), "[]")


if __name__ == "__main__":
    unittest.main()
