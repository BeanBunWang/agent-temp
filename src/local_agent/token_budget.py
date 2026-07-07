from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TokenBudget:
    max_tokens: int = 8000
    compression_threshold: float = 0.70

    @property
    def compression_watermark(self) -> int:
        return int(self.max_tokens * self.compression_threshold)


def estimate_tokens(value: Any) -> int:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    # A conservative approximation for mixed Chinese/English text.
    cjk = sum(1 for ch in value if "\u4e00" <= ch <= "\u9fff")
    other = len(value) - cjk
    return cjk + max(1, other // 4)
