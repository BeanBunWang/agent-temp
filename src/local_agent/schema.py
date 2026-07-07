from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4


TERMINAL_REASONS = {
    "final_response",
    "budget_exhausted",
    "max_steps",
    "tool_error_limit",
    "fatal_error",
}


@dataclass
class ToolResult:
    call_id: str
    tool: str
    status: str
    content: str
    structured_data: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False
    redactions: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "tool": self.tool,
            "status": self.status,
            "content": self.content,
            "structured_data": self.structured_data,
            "artifacts": self.artifacts,
            "evidence": self.evidence,
            "retryable": self.retryable,
            "redactions": self.redactions,
            "metrics": self.metrics,
        }


@dataclass
class RunState:
    task: str
    workspace: Path
    run_id: str = field(default_factory=lambda: str(uuid4()))
    constraints: list[str] = field(default_factory=list)
    loaded_skills: dict[str, str] = field(default_factory=dict)
    skill_metadata: list[dict[str, Any]] = field(default_factory=list)
    important_results: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    pending_items: list[str] = field(default_factory=list)
    failure_counts: dict[str, int] = field(default_factory=dict)
    final_answer: str | None = None
    terminal_reason: str | None = None
    step: int = 0

    def remember_result(self, result: ToolResult) -> None:
        record = result.as_dict()
        content = record.get("content", "")
        if len(content) > 900:
            record["content"] = content[:900] + "\n...[truncated in state]"
        self.important_results.append(record)
        self.important_results = self.important_results[-12:]

    def mark_failure(self, key: str) -> int:
        self.failure_counts[key] = self.failure_counts.get(key, 0) + 1
        return self.failure_counts[key]
