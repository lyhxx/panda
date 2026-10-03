import json
import unittest

from panda_infer.mic_level import LEVEL_PREFIX, format_level_line


class MicLevelFormatTest(unittest.TestCase):
    def test_line_carries_prefix_and_json(self):
        line = format_level_line(0.1234567, 0.7654321, True)

        self.assertTrue(line.startswith(LEVEL_PREFIX + " "))
        payload = json.loads(line[len(LEVEL_PREFIX) + 1:])
        self.assertAlmostEqual(payload["rms"], 0.123457, places=6)
        self.assertAlmostEqual(payload["peak"], 0.765432, places=6)
        self.assertTrue(payload["clipped"])

    def test_line_is_single_line(self):
        line = format_level_line(0.0, 0.0, False)
        self.assertNotIn("\n", line)


if __name__ == "__main__":
    unittest.main()
