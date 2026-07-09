from __future__ import annotations

import os
import re
import subprocess
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from uuid import uuid4

from .policy import PolicyError, resolve_workspace_path, validate_shell_command
from .schema import ToolResult


MAX_FILE_CHARS = 4000
MAX_SHELL_CHARS = 3000
XLSX_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


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
        path = resolve_workspace_path(self.workspace, str(path_argument(arguments)))
        if not path.is_file():
            return ToolResult(call_id, "read_file", "error", f"file not found: {path}", retryable=False)
        if path.suffix.lower() == ".xlsx":
            text, metadata = read_xlsx_preview(path)
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
            metadata = {"file_type": "text"}
        truncated = len(text) > MAX_FILE_CHARS
        content = text[:MAX_FILE_CHARS]
        if truncated:
            content += "\n...[truncated: file result exceeded limit]"
        metadata.update({"path": str(path.relative_to(self.workspace)), "chars": len(text), "truncated": truncated})
        return ToolResult(
            call_id,
            "read_file",
            "success",
            content,
            structured_data=metadata,
            evidence={"path": str(path)},
        )

    def _write_file(self, call_id: str, arguments: dict[str, Any]) -> ToolResult:
        path = resolve_workspace_path(self.workspace, str(path_argument(arguments)))
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


def read_xlsx_preview(path: Path, max_rows_per_sheet: int = 12) -> tuple[str, dict[str, Any]]:
    shared_strings: list[str] = []
    sheet_outputs: list[str] = []
    sheet_names: list[str] = []
    with zipfile.ZipFile(path) as workbook:
        names = workbook.namelist()
        if "xl/sharedStrings.xml" in names:
            shared_root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            for item in shared_root.findall(".//m:si", XLSX_NS):
                shared_strings.append("".join(t.text or "" for t in item.findall(".//m:t", XLSX_NS)))

        workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
        rel_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
        rels = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rel_root}

        for sheet in workbook_root.findall(".//m:sheet", XLSX_NS):
            sheet_name = sheet.attrib.get("name", "sheet")
            relation_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
            target = rels.get(relation_id, "")
            if not target:
                continue
            sheet_path = "xl/" + target.lstrip("/")
            root = ET.fromstring(workbook.read(sheet_path))
            rows: list[list[str]] = []
            for row in root.findall(".//m:sheetData/m:row", XLSX_NS)[:max_rows_per_sheet]:
                rows.append(read_xlsx_row(row, shared_strings))
            sheet_names.append(sheet_name)
            rendered_rows = [" | ".join(row) for row in rows]
            sheet_outputs.append(f"## Sheet: {sheet_name}\n" + "\n".join(rendered_rows))

    text = f"# XLSX Preview: {path.name}\n\n" + "\n\n".join(sheet_outputs)
    return text, {"file_type": "xlsx", "sheets": sheet_names}


def read_xlsx_row(row: ET.Element, shared_strings: list[str]) -> list[str]:
    cells_by_index: dict[int, str] = {}
    for cell in row.findall("m:c", XLSX_NS):
        ref = cell.attrib.get("r", "")
        index = column_index(ref)
        cells_by_index[index] = read_xlsx_cell(cell, shared_strings)
    if not cells_by_index:
        return []
    return [cells_by_index.get(index, "") for index in range(max(cells_by_index) + 1)]


def read_xlsx_cell(cell: ET.Element, shared_strings: list[str]) -> str:
    if cell.attrib.get("t") == "inlineStr":
        return "".join(t.text or "" for t in cell.findall(".//m:t", XLSX_NS))
    value = cell.find("m:v", XLSX_NS)
    text = "" if value is None else value.text or ""
    if cell.attrib.get("t") == "s" and text.isdigit():
        index = int(text)
        if 0 <= index < len(shared_strings):
            return shared_strings[index]
    return text


def column_index(reference: str) -> int:
    match = re.match(r"([A-Z]+)", reference)
    if not match:
        return 0
    number = 0
    for char in match.group(1):
        number = number * 26 + ord(char) - ord("A") + 1
    return number - 1


def path_argument(arguments: dict[str, Any]) -> str:
    for key in ("path", "file_path", "filepath", "filename"):
        if arguments.get(key):
            return str(arguments[key])
    return ""
