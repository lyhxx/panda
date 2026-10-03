from __future__ import annotations

import unittest

from panda_infer.benchmark import build_parser, summarize_latencies


class BenchmarkTest(unittest.TestCase):
    def test_summarize_latencies(self) -> None:
        summary = summarize_latencies([5.0, 1.0, 3.0, 2.0], 4.0)

        self.assertEqual(summary["samples"], 4)
        self.assertAlmostEqual(summary["mean_ms"], 2.75)
        self.assertAlmostEqual(summary["p50_ms"], 2.5)
        self.assertAlmostEqual(summary["p90_ms"], 5.0)
        self.assertAlmostEqual(summary["p95_ms"], 5.0)
        self.assertAlmostEqual(summary["p99_ms"], 5.0)
        self.assertAlmostEqual(summary["max_ms"], 5.0)
        self.assertAlmostEqual(summary["realtime_factor"], 0.6875)
        self.assertEqual(summary["overruns"], 1)

    def test_empty_samples_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            summarize_latencies([], 160.0)

    def test_threads_option_is_parsed(self) -> None:
        args = build_parser().parse_args(
            [
                "--meanvc2-root",
                "MeanVC2",
                "--target-wav",
                "ref.wav",
                "--source-wav",
                "src.wav",
                "--threads",
                "1",
            ]
        )

        self.assertEqual(args.threads, 1)


if __name__ == "__main__":
    unittest.main()
