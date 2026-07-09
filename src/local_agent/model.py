from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ModelAction:
    kind: str
    name: str = ""
    arguments: dict[str, Any] | None = None
    content: str = ""
    rationale: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "arguments": self.arguments or {},
            "content": self.content,
            "rationale": self.rationale,
        }


class ModelProvider(Protocol):
    def next_action(self, context: dict[str, Any]) -> ModelAction:
        ...


class MockModel:
    """Deterministic provider used for repeatable local demos and tests."""

    def next_action(self, context: dict[str, Any]) -> ModelAction:
        step = int(context.get("step", 0))
        task = str(context.get("task", ""))
        loaded_skills = context.get("loaded_skills", {})
        results = context.get("important_results", [])

        if step == 0 and "report-writer" not in loaded_skills:
            return ModelAction("load_skill", "report-writer", rationale="Need report workflow guidance.")
        if step == 1:
            return ModelAction(
                "tool",
                "search_dir",
                {"path": "data", "query": "", "max_depth": 3, "limit": 20},
                rationale="Discover available documents before reading them.",
            )
        if step == 2:
            return ModelAction(
                "tool",
                "read_file",
                {"path": "data/largemodel_scene_task_mapping_sheet2.csv"},
                rationale="Read the main source document.",
            )
        if step == 3:
            return ModelAction(
                "tool",
                "run_shell",
                {"command": "rm -rf data", "timeout": 1},
                rationale="Exercise high-risk command boundary handling in trace.",
            )
        if step == 4:
            report = self._build_report(task, results)
            return ModelAction(
                "tool",
                "write_file",
                {"path": "reports/agent_report.md", "content": report},
                rationale="Persist the final report artifact.",
            )
        if step == 5:
            return ModelAction(
                "tool",
                "run_shell",
                {"command": "ls reports", "timeout": 3},
                rationale="Collect deterministic evidence that the report exists.",
            )
        return ModelAction(
            "final",
            content=(
                "已完成示例任务：读取 data 目录内容，生成 reports/agent_report.md，并导出 trace。"
                " trace 中包含工具调用、skill 加载、压缩与高风险 shell 拒绝事件。"
            ),
            rationale="All planned work is complete.",
        )

    def _build_report(self, task: str, results: list[dict[str, Any]]) -> str:
        source = ""
        for result in results:
            if result.get("tool") == "read_file" and result.get("status") == "success":
                source = result.get("content", "")
                break
        excerpt = source[:1200] if source else "未读取到来源内容。"
        return (
            "# Agent 文档处理报告\n\n"
            f"## 任务\n{task}\n\n"
            "## 摘要\n"
            "本报告由本地 CLI Agent 生成。Agent 先按需加载报告写作 skill，"
            "再检索 data 目录、读取源文档、验证 shell 安全边界，并写入报告文件。\n\n"
            "## 关键发现\n"
            "- 推荐采用显式 Agent Loop，而不是把控制权散落在工具或提示词中。\n"
            "- 工具调用应统一返回结构化结果，失败、拒绝和超时都要进入 trace。\n"
            "- Skill 只承载流程知识，正文按需进入上下文，避免启动时消耗预算。\n"
            "- 上下文压缩应保留目标、约束、进度、重要工具结果和未完成事项。\n\n"
            "## 来源摘录\n"
            f"{excerpt}\n\n"
            "## 产物\n"
            "- reports/agent_report.md\n"
            "- trace JSON\n"
        )


class OpenAICompatibleModel:
    """Minimal OpenAI-compatible chat completions adapter.

    The model must return JSON with fields: kind, name, arguments, content, rationale.
    """

    def __init__(
        self,
        base_url_env: str = "AGENT_MODEL_BASE_URL",
        api_key_env: str = "AGENT_MODEL_API_KEY",
        model_env: str = "AGENT_MODEL_NAME",
        default_base_url: str = "https://api.openai.com/v1",
        default_model: str = "gpt-4.1-mini",
        provider_label: str = "openai-compatible",
    ) -> None:
        self.base_url = os.environ.get(base_url_env, default_base_url).rstrip("/")
        self.api_key = os.environ.get(api_key_env, "")
        self.model = os.environ.get(model_env, default_model)
        self.api_key_env = api_key_env
        self.provider_label = provider_label
        self.timeout = int(os.environ.get("AGENT_MODEL_TIMEOUT", "90"))
        if not self.api_key:
            raise RuntimeError(f"{api_key_env} is required for {provider_label} provider")

    def next_action(self, context: dict[str, Any]) -> ModelAction:
        prompt = (
            "You are controlling a local agent runtime. Return only JSON with keys "
            "kind(tool|load_skill|final), name, arguments, content, rationale.\n\n"
            f"Context:\n{json.dumps(context, ensure_ascii=False)}"
        )
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return a single valid JSON object only. Do not use markdown. "
                        "Respect tool policy, workspace boundaries, and the available action schema."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        raw = payload["choices"][0]["message"]["content"]
        data = parse_action_json(raw)
        return ModelAction(
            str(data.get("kind", "")),
            str(data.get("name", "")),
            data.get("arguments") or {},
            str(data.get("content", "")),
            str(data.get("rationale", "")),
        )


class DeepSeekModel(OpenAICompatibleModel):
    def __init__(self) -> None:
        super().__init__(
            base_url_env="DEEPSEEK_BASE_URL",
            api_key_env="DEEPSEEK_API_KEY",
            model_env="DEEPSEEK_MODEL",
            default_base_url="https://api.deepseek.com",
            default_model="deepseek-v4-flash",
            provider_label="deepseek",
        )


def parse_action_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("model action JSON must be an object")
    return data


def make_provider(name: str) -> ModelProvider:
    if name == "mock":
        return MockModel()
    if name == "openai-compatible":
        return OpenAICompatibleModel()
    if name == "deepseek":
        return DeepSeekModel()
    raise ValueError(f"unknown model provider: {name}")
