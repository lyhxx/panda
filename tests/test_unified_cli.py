from __future__ import annotations

import unittest

from panda_cli.cli import build_parser


class UnifiedCliTest(unittest.TestCase):
    def test_routes_command_arguments_to_selected_tool(self) -> None:
        args, remainder = build_parser().parse_known_args(
            ["realtime", "--model", "40ms", "--device", "cpu"]
        )

        self.assertEqual(args.command, "realtime")
        self.assertEqual(
            remainder,
            ["--model", "40ms", "--device", "cpu"],
        )

    def test_routes_device_arguments(self) -> None:
        args, remainder = build_parser().parse_known_args(
            ["devices", "--json"]
        )

        self.assertEqual(args.command, "devices")
        self.assertEqual(remainder, ["--json"])

    def test_routes_doctor_arguments(self) -> None:
        args, remainder = build_parser().parse_known_args(
            ["doctor", "--json"]
        )

        self.assertEqual(args.command, "doctor")
        self.assertEqual(remainder, ["--json"])

    def test_routes_benchmark_arguments(self) -> None:
        args, remainder = build_parser().parse_known_args(
            ["benchmark", "--model", "40ms"]
        )

        self.assertEqual(args.command, "benchmark")
        self.assertEqual(remainder, ["--model", "40ms"])

    def test_routes_simulate_arguments(self) -> None:
        args, remainder = build_parser().parse_known_args(
            ["simulate", "--repeat", "3", "--fast"]
        )

        self.assertEqual(args.command, "simulate")
        self.assertEqual(remainder, ["--repeat", "3", "--fast"])

    def test_routes_route_check_arguments(self) -> None:
        args, remainder = build_parser().parse_known_args(
            ["route-check", "--json"]
        )

        self.assertEqual(args.command, "route-check")
        self.assertEqual(remainder, ["--json"])


if __name__ == "__main__":
    unittest.main()
