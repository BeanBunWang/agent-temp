from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from local_agent.model import DeepSeekModel, parse_action_json


class ModelConfigTest(unittest.TestCase):
    def test_parse_action_json_accepts_plain_json(self) -> None:
        action = parse_action_json('{"kind":"final","content":"done"}')
        self.assertEqual(action["kind"], "final")

    def test_parse_action_json_accepts_code_fence(self) -> None:
        action = parse_action_json('```json\n{"kind":"tool","name":"search_dir","arguments":{"path":"."}}\n```')
        self.assertEqual(action["name"], "search_dir")

    def test_deepseek_provider_uses_deepseek_env_without_leaking_key(self) -> None:
        env = {
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
            "DEEPSEEK_API_KEY": "test-secret",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "AGENT_MODEL_TIMEOUT": "77",
        }
        with patch.dict(os.environ, env, clear=False):
            provider = DeepSeekModel()
        self.assertEqual(provider.base_url, "https://api.deepseek.com")
        self.assertEqual(provider.model, "deepseek-v4-flash")
        self.assertEqual(provider.api_key_env, "DEEPSEEK_API_KEY")
        self.assertEqual(provider.timeout, 77)


if __name__ == "__main__":
    unittest.main()
