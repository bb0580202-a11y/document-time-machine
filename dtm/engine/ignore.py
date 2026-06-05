"""分类：黑(忽略)/白(重点保护)/灰(默认仍备份)。失败方向只能是'多备'(INV-2)。"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

from ..config import IGNORE_PATTERNS, PROTECTED_EXTS


@dataclass
class Decision:
    ignored: bool
    protected: bool


def classify(name: str) -> Decision:
    base = Path(name).name
    for pat in IGNORE_PATTERNS:
        if fnmatch.fnmatch(base, pat):
            return Decision(ignored=True, protected=False)
    ext = Path(base).suffix.lower()
    return Decision(ignored=False, protected=ext in PROTECTED_EXTS)


def default_gitignore() -> str:
    return "\n".join(IGNORE_PATTERNS) + "\n"
