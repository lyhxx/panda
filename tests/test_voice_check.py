from __future__ import annotations

import unittest

from panda_infer.voice_check import CONTROL_FLOOR, cosine_similarity, evaluate_report


class CosineSimilarityTest(unittest.TestCase):
    def test_identical_vectors_score_one(self) -> None:
        self.assertAlmostEqual(
            cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]),
            1.0,
        )

    def test_scaled_vectors_still_score_one(self) -> None:
        self.assertAlmostEqual(
            cosine_similarity([1.0, 0.0], [7.5, 0.0]),
            1.0,
        )

    def test_orthogonal_vectors_score_zero(self) -> None:
        self.assertAlmostEqual(
            cosine_similarity([1.0, 0.0], [0.0, 1.0]),
            0.0,
        )

    def test_opposite_vectors_score_minus_one(self) -> None:
        self.assertAlmostEqual(
            cosine_similarity([1.0, 1.0], [-1.0, -1.0]),
            -1.0,
        )

    def test_length_mismatch_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            cosine_similarity([1.0, 2.0], [1.0])

    def test_empty_vectors_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            cosine_similarity([], [])

    def test_zero_vector_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            cosine_similarity([0.0, 0.0], [1.0, 1.0])


class EvaluateReportTest(unittest.TestCase):
    """The pass/fail gate of the only objective voice-change check."""

    @staticmethod
    def healthy() -> dict:
        # Development-host numbers from DEVELOPMENT 3.4.
        return {
            "control_converted_vs_source": 0.7323,
            "source_vs_target": 0.2831,
            "converted_vs_target": 0.7010,
            "moved_toward_target": True,
        }

    def test_movement_toward_the_target_passes(self) -> None:
        ok, reason = evaluate_report(self.healthy())
        self.assertTrue(ok)
        self.assertIn("目标", reason)

    def test_no_movement_fails(self) -> None:
        report = self.healthy()
        report["moved_toward_target"] = False

        ok, reason = evaluate_report(report)

        self.assertFalse(ok)
        self.assertIn("推向目标", reason)

    def test_a_pipeline_that_lost_the_speaker_fails_even_when_moved(
        self,
    ) -> None:
        # Without the control gate, "closer to the target" passes on noise
        # from a pipeline that destroyed every identity equally.
        report = self.healthy()
        report["control_converted_vs_source"] = CONTROL_FLOOR - 0.1

        ok, reason = evaluate_report(report)

        self.assertFalse(ok)
        self.assertIn("流水线", reason)


if __name__ == "__main__":
    unittest.main()
