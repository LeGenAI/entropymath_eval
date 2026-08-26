import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_website_results import grade, summarize


class PreparationTests(unittest.TestCase):
    def rows(self):
        return [
            {"id": 0, "run_idx": 0, "error": "timeout"},
            {"id": 0, "run_idx": 1, "gold_answer": "42", "final_answer": "42"},
            {"id": 0, "run_idx": 2, "gold_answer": "42", "final_answer": ""},
        ]

    def test_errors_keep_first_attempt_and_denominator(self):
        result = summarize(self.rows(), 1)
        self.assertEqual(result["accuracy_at_1"], 0)
        self.assertEqual(result["run_accuracy"], 1 / 3)
        self.assertEqual(result["pass_at_3"], 1)
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["problem_stats"]["0"], {"correct": 1, "total": 3})

    def test_duplicate_missing_and_extra_runs_rejected(self):
        for rows in [self.rows() + self.rows()[:1], self.rows()[1:],
                     self.rows() + [{"id": 0, "run_idx": 3}]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                summarize(rows, 1)

    def test_all_errors_still_count(self):
        rows = [{"id": 0, "run_idx": i, "error": "timeout"} for i in range(3)]
        result = summarize(rows, 1)
        self.assertEqual(result["run_count"], 3)
        self.assertEqual(result["pass_at_3"], 0)

    def test_strict_choice_symbols(self):
        self.assertTrue(grade({"gold_answer": "③", "final_answer": "③"}))
        self.assertFalse(grade({"gold_answer": "③", "final_answer": "3"}))

    def test_numeric_answers_and_empty_extraction(self):
        self.assertTrue(grade({"gold_answer": "42", "final_answer": "42.0"}))
        self.assertTrue(grade({"gold_answer": 0, "final_answer": 0}))
        self.assertFalse(grade({"gold_answer": "42", "final_answer": None}))
        self.assertFalse(grade({"gold_answer": "42", "final_answer": "text"}))

    def test_unsupported_gold_is_not_silently_graded(self):
        for gold in [None, "", "1/2", "0.5", "NaN"]:
            with self.subTest(gold=gold), self.assertRaises(ValueError):
                grade({"gold_answer": gold, "final_answer": ""})

    def test_manual_flags_are_preserved(self):
        self.assertTrue(grade({"correct": True}))
        self.assertFalse(grade({"correct": False}))
        self.assertFalse(grade({"correct": True, "timeout": True}))
        with self.assertRaises(ValueError):
            grade({"correct": "false"})


if __name__ == "__main__":
    unittest.main()
