from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_agent.config import load_env_files


class ConfigTest(unittest.TestCase):
    def test_load_env_files_does_not_override_existing_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".env").write_text("A=from_file\nB='quoted'\n", encoding="utf-8")
            with patch.dict(os.environ, {"A": "from_shell"}, clear=False):
                loaded = load_env_files(Path(tmp))
                self.assertEqual([p.name for p in loaded], [".env"])
                self.assertEqual(os.environ["A"], "from_shell")
                self.assertEqual(os.environ["B"], "quoted")


if __name__ == "__main__":
    unittest.main()
