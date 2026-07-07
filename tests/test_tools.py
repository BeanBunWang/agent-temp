from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_agent.tools import ToolExecutor


class ToolExecutorTest(unittest.TestCase):
    def test_write_and_read_inside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tools = ToolExecutor(Path(tmp))
            write = tools.execute("write_file", {"path": "a/b.txt", "content": "hello"})
            self.assertEqual(write.status, "success")
            read = tools.execute("read_file", {"path": "a/b.txt"})
            self.assertEqual(read.status, "success")
            self.assertIn("hello", read.content)

    def test_path_escape_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tools = ToolExecutor(Path(tmp))
            result = tools.execute("read_file", {"path": "../secret.txt"})
            self.assertEqual(result.status, "denied")

    def test_high_risk_shell_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tools = ToolExecutor(Path(tmp))
            result = tools.execute("run_shell", {"command": "rm -rf ."})
            self.assertEqual(result.status, "denied")

    def test_large_file_result_is_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "large.txt").write_text("x" * 5000, encoding="utf-8")
            tools = ToolExecutor(Path(tmp))
            result = tools.execute("read_file", {"path": "large.txt"})
            self.assertEqual(result.status, "success")
            self.assertTrue(result.structured_data["truncated"])
            self.assertIn("truncated", result.content)

    def test_allowed_shell_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "x.txt").write_text("hello", encoding="utf-8")
            tools = ToolExecutor(Path(tmp))
            result = tools.execute("run_shell", {"command": "ls ."})
            self.assertEqual(result.status, "success")
            self.assertIn("x.txt", result.content)

    def test_shell_timeout_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tools = ToolExecutor(Path(tmp))
            result = tools.execute("run_shell", {"command": "sleep 2", "timeout": 1})
            self.assertEqual(result.status, "timeout")
            self.assertTrue(result.retryable)


if __name__ == "__main__":
    unittest.main()
