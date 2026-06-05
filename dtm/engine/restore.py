"""安全还原：还原前快照→把旧版导出为旁边的新文件→绝不覆盖当前文件（INV-3）。"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

from .repo import GitRepo
from .backup import do_backup


@dataclass
class RestoreResult:
    restored_path: str
    pre_restore_commit: str


@dataclass
class VersionRestoreResult:
    restored_paths: list[str]      # 这一版每个变更文件各另存的新路径
    pre_restore_commit: str


_FS_NAME_MAX = 255   # 主流文件系统单个文件名字节上限


def _truncate_stem(stem: str, reserved: int) -> str:
    """按 UTF-8 字节把主体截到预算内,且不切坏多字节字符(中文 1 字=3 字节)。"""
    budget = _FS_NAME_MAX - reserved
    b = stem.encode("utf-8")
    if len(b) <= budget:
        return stem
    return b[:max(0, budget)].decode("utf-8", errors="ignore")


def _export_beside(repo: GitRepo, folder: Path, commit_id: str, rel_path: str) -> str:
    """把目标版本的某文件导出为旁边的新文件,绝不覆盖当前文件(INV-3)。
    副本名带秒级时间戳(唯一、自解释);超长原名只截主体,绝不截掉时间戳/扩展名;
    时间戳用纯数字(ASCII),省字节、跨平台安全(不含 \\ / : * ? \" < > |)。"""
    data = repo.show_file(commit_id, rel_path)
    src = Path(rel_path)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")   # 跨平台,避免 %-m
    suffix = src.suffix

    def build(extra: str = "") -> Path:
        tag = f"_恢复自{ts}{extra}"
        stem = _truncate_stem(src.stem, len((tag + suffix).encode("utf-8")))
        return folder / src.parent / f"{stem}{tag}{suffix}"

    out = build()
    n = 1
    while out.exists():            # 极端同秒兜底
        out = build(f"({n})")
        n += 1
    out.write_bytes(data)
    return str(out)


def safe_restore(repo: GitRepo, folder: Path, commit_id: str, rel_path: str) -> RestoreResult:
    # 还原=旁存副本,绝不碰原文件(INV-3):原文件被 Word 开着也不冲突,故不查占用锁。
    folder = Path(folder)
    pre = do_backup(repo, folder, source="pre-restore")  # ① 还原前快照
    out = _export_beside(repo, folder, commit_id, rel_path)  # ② 导出旁边
    return RestoreResult(restored_path=out, pre_restore_commit=pre.commit_id)


def restore_version(repo: GitRepo, folder: Path, commit_id: str) -> VersionRestoreResult:
    """还原"这一版"——把该版变更过的每个文件各另存一份到旁边(所见即所还原)。
    pre-restore 快照只做一次;绝不覆盖当前文件(INV-3)。"""
    from . import listing                                 # 延迟 import,避免环
    folder = Path(folder)
    names = [c.name for c in listing.changed_files(repo, commit_id)]
    pre = do_backup(repo, folder, source="pre-restore")  # ① 还原前快照一次
    outs = [_export_beside(repo, folder, commit_id, rel) for rel in names]  # ② 逐文件导出
    return VersionRestoreResult(restored_paths=outs, pre_restore_commit=pre.commit_id)
