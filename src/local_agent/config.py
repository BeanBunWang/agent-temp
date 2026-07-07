from __future__ import annotations

import os
from pathlib import Path


def load_env_files(cwd: Path | None = None) -> list[Path]:
    """Load simple KEY=VALUE pairs from .env files without overriding shell env."""
    root = (cwd or Path.cwd()).resolve()
    loaded: list[Path] = []
    for name in (".env", ".env.local"):
        path = root / name
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
        loaded.append(path)
    return loaded
