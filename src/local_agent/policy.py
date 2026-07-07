from __future__ import annotations

import shlex
from pathlib import Path


class PolicyError(Exception):
    pass


def resolve_workspace_path(workspace: Path, user_path: str | Path) -> Path:
    root = workspace.resolve()
    candidate = Path(user_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise PolicyError(f"path escapes workspace: {user_path}")
    return resolved


HIGH_RISK_COMMANDS = {
    "rm",
    "rmdir",
    "mv",
    "chmod",
    "chown",
    "sudo",
    "su",
    "curl",
    "wget",
    "ssh",
    "scp",
    "python",
    "python3",
    "perl",
    "ruby",
    "node",
    "npm",
    "pnpm",
    "pip",
    "git",
}

SHELL_OPERATORS = {"|", ">", ">>", "<", "&&", "||", ";", "&", "$(", "`"}
ALLOWLIST_COMMANDS = {"ls", "find", "wc", "cat", "head", "tail", "pwd", "sleep"}


def validate_shell_command(command: str) -> list[str]:
    stripped = command.strip()
    if not stripped:
        raise PolicyError("empty shell command")
    for op in SHELL_OPERATORS:
        if op in stripped:
            raise PolicyError(f"shell operator is not allowed: {op}")
    try:
        parts = shlex.split(stripped)
    except ValueError as exc:
        raise PolicyError(f"invalid shell quoting: {exc}") from exc
    if not parts:
        raise PolicyError("empty shell command")
    executable = Path(parts[0]).name
    if executable in HIGH_RISK_COMMANDS:
        raise PolicyError(f"high-risk command is denied: {executable}")
    if executable not in ALLOWLIST_COMMANDS:
        raise PolicyError(f"command is not in allowlist: {executable}")
    return parts
