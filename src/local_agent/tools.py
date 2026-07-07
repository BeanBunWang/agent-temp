from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from .policy import PolicyError, resolve_workspace_path, validate_shell_command
from .schema import ToolResult


MAX_FILE_CHARS = 4000
MAX_SHELL_CHARS = 3000


class ToolExecutor:
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        call_id = str(uuid4())
        started = time.time()
        try:
            if name == "read_file":
                result = self._read_file(call_id, arguments)
            elif name == "write_file":
                result = self._write_file(call_id, arguments)
            elif name == "search_dir":
                result = self._search_dir(call_id, arguments)
            elif name == "run_shell":
                result = self._run_shell(call_id, arguments)
            else:
                result = ToolResult(call_id, name, "error", f"unknown tool: {name}", retryable=False)
        except PolicyError as exc:
            result = ToolResult(call_id, name, "denied", str(exc), retryable=False)
        except TimeoutError as exc:
            result = ToolResult(call_id, name, "timeout", str(exc), retryable=True)
        except Exception as exc:  # Defensive normalization keeps loop invariants intact.
            result = ToolResult(call_id, name, "error", f"{type(exc).__name__}: {exc}", retryable=True)
        result.metrics["duration_ms"] = int((time.time() - started) * 1000)
        return result

    def _read_file(self, call_id: str, arguments: dict[str, Any]) -> ToolResult:
        path = resolve_workspace_path(self.workspace, str(arguments.get("path", "")))
        if not path.is_file():
            return ToolResult(call_id, "read_file", "error", f"file not found: {path}", retryable=False)
        text = path.read_text(encoding="utf-8", errors="replace")
        truncated = len(text) > MAX_FILE_CHARS
        content = text[:MAX_FILE_CHARS]
        if truncated:
            content += "\n...[truncated: file result exceeded limit]"
        return ToolResult(
            call_id,
            "read_file",
            "success",
            content,
            structured_data={"path": str(path.relative_to(self.workspace)), "chars": len(text), "truncated": truncated},
            evidence={"path": str(path)},
        )

    def _write_file(self, call_id: str, arguments: dict[str, Any]) -> ToolResult:
        path = resolve_workspace_path(self.workspace, str(arguments.get("path", "")))
        content = str(arguments.get("content", ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ToolResult(
            call_id,
            "write_file",
            "success",
            f"wrote {len(content)} chars to {path.relative_to(self.workspace)}",
            structured_data={"path": str(path.relative_to(self.workspace)), "chars": len(content)},
            artifacts=[str(path)],
            evidence={"path": str(path)},
        )

    def _search_dir(self, call_id: str, arguments: dict[str, Any]) -> ToolResult:
        base = resolve_workspace_path(self.workspace, str(arguments.get("path", ".")))
        query = str(arguments.get("query", "")).lower()
        max_depth = int(arguments.get("max_depth", 4))
        limit = int(arguments.get("limit", 40))
        if not base.exists():
            return ToolResult(call_id, "search_dir", "error", f"directory not found: {base}", retryable=False)
        if not base.is_dir():
            return ToolResult(call_id, "search_dir", "error", f"not a directory: {base}", retryable=False)

        matches: list[dict[str, Any]] = []
        for root, dirs, files in os.walk(base):
            root_path = Path(root)
            rel_depth = len(root_path.relative_to(base).parts)
            if rel_depth >= max_depth:
                dirs[:] = []
            for filename in files:
                path = root_path / filename
                rel = str(path.relative_to(self.workspace))
                matched = not query or query in filename.lower()
                snippet = ""
                if query and not matched:
                    try:
                        text = path.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        text = ""
                    idx = text.lower().find(query)
                    if idx >= 0:
                        matched = True
                        snippet = text[max(0, idx - 80) : idx + 160].replace("\n", " ")
                if matched:
                    matches.append({"path": rel, "snippet": snippet})
                    if len(matches) >= limit:
                        break
            if len(matches) >= limit:
                break
        lines = [m["path"] + (f" :: {m['snippet']}" if m["snippet"] else "") for m in matches]
        return ToolResult(
            call_id,
            "search_dir",
            "success",
            "\n".join(lines) if lines else "no matches",
            structured_data={"matches": matches, "truncated": len(matches) >= limit},
            evidence={"base": str(base)},
        )

    def _run_shell(self, call_id: str, arguments: dict[str, Any]) -> ToolResult:
        command = str(arguments.get("command", ""))
        timeout = min(max(int(arguments.get("timeout", 5)), 1), 10)
        parts = validate_shell_command(command)
        try:
            completed = subprocess.run(
                parts,
                cwd=self.workspace,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"shell command timed out after {timeout}s: {command}") from exc
        output = (completed.stdout or "") + (completed.stderr or "")
        truncated = len(output) > MAX_SHELL_CHARS
        if truncated:
            output = output[:MAX_SHELL_CHARS] + "\n...[truncated: shell output exceeded limit]"
        status = "success" if completed.returncode == 0 else "error"
        return ToolResult(
            call_id,
            "run_shell",
            status,
            output,
            structured_data={"command": command, "returncode": completed.returncode, "truncated": truncated},
            evidence={"cwd": str(self.workspace)},
            retryable=completed.returncode != 0,
        )
