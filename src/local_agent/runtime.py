from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .model import ModelProvider
from .policy import PolicyError
from .schema import RunState, ToolResult
from .skills import SkillRegistry
from .token_budget import TokenBudget, estimate_tokens
from .tools import ToolExecutor
from .trace import TraceRecorder


class AgentRuntime:
    def __init__(
        self,
        model: ModelProvider,
        workspace: Path,
        trace_path: Path,
        max_steps: int = 10,
        budget: TokenBudget | None = None,
    ) -> None:
        self.model = model
        self.workspace = workspace.resolve()
        self.trace_path = trace_path
        self.max_steps = max_steps
        self.budget = budget or TokenBudget()
        self.trace = TraceRecorder()
        self.tools = ToolExecutor(self.workspace)
        self.skills = SkillRegistry(self.workspace)

    def run(self, task: str) -> RunState:
        started = time.time()
        state = RunState(
            task=task,
            workspace=self.workspace,
            constraints=[
                "workspace paths only",
                "no secrets in prompts or trace",
                "high-risk shell commands require denial",
            ],
            skill_metadata=self.skills.metadata(),
            pending_items=["discover source files", "load relevant skill", "write final artifact"],
        )
        self.trace.emit(
            "run_started",
            run_id=state.run_id,
            task=task,
            workspace=str(self.workspace),
            tool_names=["read_file", "write_file", "search_dir", "run_shell"],
            skill_metadata=state.skill_metadata,
        )

        auto_skills = self.skills.suggest_for_task(task)
        if auto_skills:
            self.trace.emit("skill_suggested", skills=auto_skills, reason="task trigger matched metadata")
            for skill_name in auto_skills:
                if skill_name not in state.loaded_skills:
                    self._load_skill(state, skill_name)

        try:
            for step in range(self.max_steps):
                state.step = step
                context = self._build_context(state)
                token_count = estimate_tokens(context)
                self.trace.emit(
                    "token_estimate",
                    step=step,
                    estimated_tokens=token_count,
                    max_tokens=self.budget.max_tokens,
                    compression_watermark=self.budget.compression_watermark,
                )
                if token_count > self.budget.max_tokens:
                    state.terminal_reason = "budget_exhausted"
                    self.trace.emit("boundary", boundary="budget_exhausted", estimated_tokens=token_count)
                    break
                if token_count >= self.budget.compression_watermark:
                    before = token_count
                    self._compress_state(state)
                    after_context = self._build_context(state)
                    after = estimate_tokens(after_context)
                    self.trace.emit(
                        "compression_triggered",
                        step=step,
                        before_tokens=before,
                        after_tokens=after,
                        preserved=["task", "constraints", "loaded_skills", "important_results", "pending_items"],
                    )
                    context = after_context

                action_started = time.time()
                self.trace.emit("model_call_started", step=step, provider=type(self.model).__name__)
                action = self.model.next_action(context)
                self.trace.emit(
                    "model_call_completed",
                    step=step,
                    duration_ms=int((time.time() - action_started) * 1000),
                    action=action.as_dict(),
                )

                if action.kind == "final":
                    state.final_answer = action.content
                    if self._needs_report_artifact(state) and not self._has_report_artifact(state):
                        self.trace.emit(
                            "boundary",
                            boundary="final_artifact_fallback",
                            reason="model returned final response before writing requested report",
                        )
                        self._execute_tool(
                            state,
                            "write_file",
                            {"path": "reports/agent_report.md", "content": action.content},
                        )
                    state.terminal_reason = "final_response"
                    self.trace.emit("final_response", step=step, content=action.content)
                    break
                if action.kind == "load_skill":
                    self._load_skill(state, action.name)
                    continue
                if action.kind == "tool":
                    result = self._execute_tool(state, action.name, action.arguments or {})
                    if result.status in {"error", "timeout", "denied"}:
                        failures = state.mark_failure(f"{result.tool}:{result.status}:{result.content[:80]}")
                        self.trace.emit(
                            "boundary",
                            boundary=f"tool_{result.status}",
                            tool=result.tool,
                            failures=failures,
                            retryable=result.retryable,
                            content=result.content,
                        )
                        if failures >= 3:
                            state.terminal_reason = "tool_error_limit"
                            break
                    continue

                self.trace.emit("boundary", boundary="invalid_model_action", action=action.as_dict())
                state.terminal_reason = "fatal_error"
                break
            else:
                state.terminal_reason = "max_steps"
        except Exception as exc:  # Final guard so a trace is still written.
            state.terminal_reason = "fatal_error"
            self.trace.emit("boundary", boundary="fatal_error", error=f"{type(exc).__name__}: {exc}")

        if not state.terminal_reason:
            state.terminal_reason = "fatal_error"
        self.trace.emit(
            "run_completed",
            run_id=state.run_id,
            terminal_reason=state.terminal_reason,
            duration_ms=int((time.time() - started) * 1000),
            final_answer=state.final_answer,
        )
        self.trace.write(
            self.trace_path,
            {
                "run_id": state.run_id,
                "task": task,
                "workspace": str(self.workspace),
                "terminal_reason": state.terminal_reason,
                "final_answer": state.final_answer,
            },
        )
        return state

    def _build_context(self, state: RunState) -> dict[str, Any]:
        return {
            "run_id": state.run_id,
            "task": state.task,
            "constraints": state.constraints,
            "step": state.step,
            "summary": state.summary,
            "pending_items": state.pending_items,
            "skill_metadata": state.skill_metadata,
            "loaded_skills": state.loaded_skills,
            "important_results": state.important_results,
            "failure_counts": state.failure_counts,
            "available_tools": ["read_file", "write_file", "search_dir", "run_shell"],
        }

    def _compress_state(self, state: RunState) -> None:
        kept_results: list[dict[str, Any]] = []
        for result in state.important_results[-5:]:
            compact = {
                "tool": result.get("tool"),
                "status": result.get("status"),
                "content": str(result.get("content", ""))[:500],
                "structured_data": result.get("structured_data", {}),
                "artifacts": result.get("artifacts", []),
            }
            kept_results.append(compact)
        state.summary = (
            f"Task: {state.task}\n"
            f"Loaded skills: {', '.join(state.loaded_skills) or 'none'}\n"
            f"Progress: {len(state.important_results)} tool results collected; "
            f"failures={state.failure_counts}."
        )
        state.important_results = kept_results

    def _load_skill(self, state: RunState, name: str) -> None:
        started = time.time()
        try:
            meta, content, warnings = self.skills.load(name)
            state.loaded_skills[meta.name] = content
            self.trace.emit(
                "skill_loaded",
                skill=meta.as_context(),
                chars=len(content),
                warnings=warnings,
                duration_ms=int((time.time() - started) * 1000),
            )
            for warning in warnings:
                self.trace.emit("boundary", boundary="skill_warning", skill=meta.name, warning=warning)
        except PolicyError as exc:
            state.mark_failure(f"skill:{name}")
            self.trace.emit("boundary", boundary="skill_load_denied", skill=name, content=str(exc))

    def _execute_tool(self, state: RunState, name: str, arguments: dict[str, Any]) -> ToolResult:
        self.trace.emit("tool_call_started", step=state.step, tool=name, arguments=arguments)
        result = self.tools.execute(name, arguments)
        state.remember_result(result)
        self.trace.emit("tool_call_completed", step=state.step, result=result.as_dict())
        return result

    def _needs_report_artifact(self, state: RunState) -> bool:
        return "报告" in state.task or "report" in state.task.lower()

    def _has_report_artifact(self, state: RunState) -> bool:
        for result in state.important_results:
            if result.get("tool") != "write_file" or result.get("status") != "success":
                continue
            data = result.get("structured_data", {})
            if data.get("path") == "reports/agent_report.md":
                return True
        return False
