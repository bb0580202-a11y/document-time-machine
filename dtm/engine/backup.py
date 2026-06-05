"""备份编排：写 .gitignore→git add -A→commit→完整性校验+重试一次→清单/告警。"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path

from ..config import LARGE_FILE_MB
from .repo import GitRepo
from .ignore import classify, default_gitignore
from .integrity import check
from .messages import build_message


# dtm 自己的簿记文件：仍会被提交，但不算"用户内容"，不进清单/摘要（INV-6 不暴露管道）。
_DTM_OWN_FILES = {".gitignore"}


def gitignore_text() -> str:
    return default_gitignore()


@dataclass
class BackupResult:
    committed: bool
    commit_id: str = ""
    manifest: list[str] = field(default_factory=list)   # 本次纳入备份的文件
    warnings: list[str] = field(default_factory=list)


def _scan(folder: Path):
    """返回 (纳入备份的相对路径列表, 总字节, 告警)。"""
    included, total, warnings = [], 0, []
    for p in folder.rglob("*"):
        if p.is_dir() or ".git" in p.parts:
            continue
        rel = p.relative_to(folder).as_posix()
        if rel in _DTM_OWN_FILES or classify(rel).ignored:
            continue
        size = p.stat().st_size
        total += size
        included.append(rel)
        if size > LARGE_FILE_MB * 1024 * 1024:
            warnings.append(
                f"{rel} 体积较大（{size // 1024 // 1024}MB），已备份但请留意空间。"
            )
    return included, total, warnings


def do_backup(repo: GitRepo, folder: Path, source: str = "auto") -> BackupResult:
    folder = Path(folder)
    included, total, warnings = _scan(folder)
    repo.add_all()
    if not repo.has_staged_changes():
        return BackupResult(committed=False, manifest=included, warnings=warnings)

    iso = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    files = included if included else ["(空)"]
    msg = build_message(iso, files, total, source)
    cid = repo.commit(msg)

    # 完整性校验：对纳入的 zip 系/pdf 文件，失败则重试一次（§6.6）
    for rel in included:
        ok, reason = check(folder / rel)
        if not ok:
            warnings.append(f"{reason}，已自动重新备份一次。")
            repo.add_all()
            if repo.has_staged_changes():
                cid = repo.commit(build_message(iso, files, total, source))
    return BackupResult(committed=True, commit_id=cid, manifest=included, warnings=warnings)
