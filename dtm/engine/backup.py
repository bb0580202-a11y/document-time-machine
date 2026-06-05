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
from . import flags


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

    # 完整性自检：对纳入的 zip 系/pdf 文件做一次"能否打开"体检。
    # 坏的是 Word/PDF 写出来的源文件本身——我们只是忠实存下了它，重存一遍还是同样的
    # 坏字节，修不了别人写坏的文件。故只如实告警，绝不谎称"已重新备份"(INV-5：诚实)；
    # 你之前的正常版本都安全，可随时还原回去。坏文件持久记进 .git/dtm_corrupt.json：
    # 守护后台自动备份时没开窗，这条告警飘走也不丢——开窗后相册卡片仍显 ⚠（flags）。
    corrupt = []
    for rel in included:
        ok, reason = check(folder / rel)
        if not ok:
            warnings.append(
                f"{reason}。这一版的文件本身可能就是坏的（不是备份出的问题，"
                f"是保存下来的文件就这样），已照原样存档；你之前的正常版本都还在，"
                f"可随时还原回去。"
            )
            corrupt.append(rel)
    if corrupt:
        flags.record_corrupt(repo, cid, corrupt)
    return BackupResult(committed=True, commit_id=cid, manifest=included, warnings=warnings)
