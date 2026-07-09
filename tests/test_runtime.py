from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_agent.model import ModelAction
from local_agent.runtime import AgentRuntime
from local_agent.token_budget import TokenBudget


class FinalOnlyModel:
    def next_action(self, context):
        return ModelAction("final", content="# Report\n\nDone.")


class RuntimeTest(unittest.TestCase):
    def test_report_final_response_is_persisted_and_skill_autoloaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "skills" / "report-writer"
            skill_dir.mkdir(parents=True)
            skill_dir.joinpath("SKILL.md").write_text(
                "---\n"
                "name: report-writer\n"
                "description: Report writer\n"
                "triggers: 报告,report\n"
                "tools: read_file,write_file\n"
                "risk: low\n"
                "---\n"
                "# Report Writer\n",
                encoding="utf-8",
            )
            trace = root / "trace.json"
            runtime = AgentRuntime(FinalOnlyModel(), root, trace, max_steps=2, budget=TokenBudget())
            state = runtime.run("生成报告")

            self.assertEqual(state.terminal_reason, "final_response")
            self.assertIn("report-writer", state.loaded_skills)
            self.assertEqual(root.joinpath("reports/agent_report.md").read_text(encoding="utf-8"), "# Report\n\nDone.")
            trace_text = trace.read_text(encoding="utf-8")
            self.assertIn("skill_loaded", trace_text)
            self.assertIn("final_artifact_fallback", trace_text)


if __name__ == "__main__":
    unittest.main()
