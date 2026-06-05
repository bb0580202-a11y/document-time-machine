"""仓库体积与版本数（为膨胀实验/stats 服务）。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .repo import GitRepo


@dataclass
class Stats:
    git_bytes: int
    version_count: int


def _dir_size(path: Path) -> int:
    total = 0
    for root, _d, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def repo_stats(repo: GitRepo) -> Stats:
    return Stats(
        git_bytes=_dir_size(repo.folder / ".git"),
        version_count=len(repo.log()),
    )
