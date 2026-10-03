"""A bad --python must be a clean error, never a traceback or a hang."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from panda_infer.realtime_cli import print_devices
from panda_infer.route_check import main as route_check_main


def missing_python() -> str:
    directory = tempfile.mkdtemp(prefix="panda-no-python-")
    return str(Path(directory) / "no-such-python.exe")


class DeviceQueryRobustnessTest(unittest.TestCase):
    def test_json_devices_reports_a_missing_interpreter(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            code = print_devices(missing_python(), as_json=True)

        self.assertEqual(code, 2)
        self.assertIn("error:", buffer.getvalue())

    def test_text_devices_reports_a_missing_interpreter(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            code = print_devices(missing_python())

        self.assertEqual(code, 2)
        self.assertIn("error:", buffer.getvalue())

    def test_route_check_reports_a_missing_interpreter(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            code = route_check_main(
                ["--python", missing_python(), "--json"]
            )

        self.assertEqual(code, 2)
        self.assertIn("error:", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
