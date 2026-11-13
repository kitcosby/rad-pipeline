"""Executor tests (WP3): allowlist, capture, exit codes, timeout, cap."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radpipe.executor import CommandNotAllowedError, Executor

PY = sys.executable
HELPERS = Path(__file__).resolve().parent / "helpers"


class TestExecutor(unittest.TestCase):
    def setUp(self):
        self.executor = Executor({PY})

    def test_runs_and_captures_output(self):
        outcome = self.executor.run([PY, "-c", "print('hello pipe')"], timeout_s=10)
        self.assertTrue(outcome.succeeded)
        self.assertEqual(outcome.exit_code, 0)
        self.assertIn("hello pipe", outcome.stdout)

    def test_non_allowlisted_command_refused(self):
        with self.assertRaises(CommandNotAllowedError):
            self.executor.run(["/bin/echo", "hi"], timeout_s=5)
        with self.assertRaises(CommandNotAllowedError):
            self.executor.check_allowed([])

    def test_exit_code_passthrough(self):
        outcome = self.executor.run(
            [PY, str(HELPERS / "fail.py"), "3"], timeout_s=10
        )
        self.assertEqual(outcome.exit_code, 3)
        self.assertFalse(outcome.succeeded)
        self.assertFalse(outcome.timed_out)

    def test_timeout_kills_and_reports(self):
        outcome = self.executor.run(
            [PY, str(HELPERS / "sleep.py"), "30"], timeout_s=0.5
        )
        self.assertTrue(outcome.timed_out)
        self.assertIsNone(outcome.exit_code)
        self.assertFalse(outcome.succeeded)

    def test_output_cap_truncates_and_flags(self):
        small = Executor({PY}, output_cap=100)
        outcome = small.run([PY, "-c", "print('x' * 5000)"], timeout_s=10)
        self.assertTrue(outcome.truncated)
        self.assertLessEqual(len(outcome.stdout), 101)  # cap + newline slack


if __name__ == "__main__":
    unittest.main()
