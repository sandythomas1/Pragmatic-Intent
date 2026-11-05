"""Spec 009 T4: length preflight and max_model_len sizing (invented fixtures only)."""

import unittest

from src.llm import preflight as pf

SENTINEL = "zq-sentinel-long"


def words(messages):
    """Stand-in token counter: whitespace words over all message contents."""
    return sum(len(message["content"].split()) for message in messages)


def prompt(n_words, filler="w"):
    return [{"role": "system", "content": "instr"}, {"role": "user", "content": " ".join([filler] * (n_words - 1))}]


class RequireFitTests(unittest.TestCase):
    def test_fitting_prompts_report_counts_only(self):
        report = pf.require_fit([prompt(10), prompt(40)], words, max_tokens=8, max_model_len=64)
        self.assertEqual(report.as_dict(), {"prompts": 2, "max_prompt_tokens": 40, "over_limit": 0,
                                            "max_tokens": 8, "max_model_len": 64})

    def test_boundary_prompt_exactly_filling_the_window_fits(self):
        report = pf.require_fit([prompt(56)], words, max_tokens=8, max_model_len=64)
        self.assertEqual(report.over_limit, 0)

    def test_ac_009_3c_one_token_over_refuses_without_ids_or_text(self):
        calls = []

        def counting(messages):
            calls.append(1)
            return words(messages)

        with self.assertRaises(pf.PreflightError) as caught:
            pf.require_fit([prompt(10), prompt(57, SENTINEL), prompt(5)], counting, max_tokens=8, max_model_len=64)
        message = str(caught.exception)
        self.assertIn("1 of 3", message)
        self.assertNotIn("zq-sentinel", message)
        self.assertEqual(len(calls), 3, "every prompt is counted before deciding")

    def test_bad_limits_and_counters_are_refused(self):
        with self.assertRaises(ValueError):
            pf.require_fit([prompt(3)], words, max_tokens=64, max_model_len=64)
        with self.assertRaises(ValueError):
            pf.require_fit([prompt(3)], lambda m: 0, max_tokens=8, max_model_len=64)
        with self.assertRaises(ValueError):
            pf.require_fit([prompt(3)], lambda m: 3.5, max_tokens=8, max_model_len=64)
        with self.assertRaises(ValueError):
            pf.require_fit([], words, max_tokens=8, max_model_len=64)

    def test_prompts_are_never_modified(self):
        original = prompt(57)
        snapshot = [dict(message) for message in original]
        with self.assertRaises(pf.PreflightError):
            pf.require_fit([original], words, max_tokens=8, max_model_len=64)
        self.assertEqual(original, snapshot)


class SizingTests(unittest.TestCase):
    def test_rounds_up_to_the_next_512_strictly_above_the_sum(self):
        self.assertEqual(pf.required_model_len(700, 256), 1024)
        self.assertEqual(pf.required_model_len(256, 256), 1024, "an exact multiple still gets a margin")
        self.assertEqual(pf.required_model_len(1, 1), 512)
        self.assertEqual(pf.required_model_len(767, 256), 1024, "1023 still has one token of margin")
        self.assertEqual(pf.required_model_len(768, 256), 1536)

    def test_size_uses_the_longest_prompt(self):
        self.assertEqual(pf.size_model_len([prompt(100), prompt(700), prompt(5)], words, max_tokens=256), 1024)

    def test_sized_length_always_passes_require_fit(self):
        prompts = [prompt(n) for n in (3, 255, 256, 257, 511, 768)]
        limit = pf.size_model_len(prompts, words, max_tokens=256)
        self.assertEqual(pf.require_fit(prompts, words, max_tokens=256, max_model_len=limit).over_limit, 0)

    def test_invalid_sizing_inputs_are_refused(self):
        for args in ((0, 256), (10, 0)):
            with self.assertRaises(ValueError):
                pf.required_model_len(*args)
        with self.assertRaises(ValueError):
            pf.size_model_len([], words, max_tokens=256)


if __name__ == "__main__":
    unittest.main()
