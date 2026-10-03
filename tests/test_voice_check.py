from __future__ import annotations

import unittest

from panda_infer.voice_check import cosine_similarity


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


if __name__ == "__main__":
    unittest.main()
