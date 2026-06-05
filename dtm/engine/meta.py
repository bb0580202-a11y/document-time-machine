"""里程碑(git tag) + 自由备注(git notes)。备注/里程碑都不触碰用户文件、不产生新快照。"""
from __future__ import annotations

import subprocess
import time

from ..config import NOTES_REF
from . import probe
from .repo import GitRepo
from .git_exe import git_path, subprocess_prep, subprocess_kwargs


def _git(repo: GitRepo, *args, check=True):
    # 与 repo._git 对齐:走内置 git(git_path,非裸"git")+ subprocess_prep(治 0xc0000142)+
    # CREATE_NO_WINDOW + UTF-8 解码(中文 Windows 默认 GBK 会解坏)。早期漏了 → frozen Windows 上
    # 无系统 git 时 notes/tags 全失败,连累 get_album(每版调 get_note)→"历史读不出来"。
    _t = time.perf_counter()
    try:
        with subprocess_prep():
            return subprocess.run([git_path(), "-C", str(repo.folder), *args],
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  check=check, **subprocess_kwargs())
    finally:
        probe.record_git(args, time.perf_counter() - _t)   # 性能探针


def set_note(repo: GitRepo, commit_id: str, text: str) -> None:
    if text:
        _git(repo, "notes", f"--ref={NOTES_REF}", "add", "-f", "-m", text, commit_id)
    else:
        _git(repo, "notes", f"--ref={NOTES_REF}", "remove", commit_id, check=False)


def get_note(repo: GitRepo, commit_id: str) -> str:
    r = _git(repo, "notes", f"--ref={NOTES_REF}", "show", commit_id, check=False)
    return r.stdout.strip() if r.returncode == 0 else ""


def all_notes(repo: GitRepo) -> dict[str, str]:
    """一次取所有版本的备注(避免每版 spawn,治 Windows 卡顿)。
    git log 带 notes:%N 给备注文本,%x1e 记录分隔(备注可多行)、%x1f 字段分隔。"""
    fmt = "%x1e%H%x1f%N"
    r = _git(repo, "log", "--branches", f"--notes={NOTES_REF}",
             f"--format={fmt}", check=False)
    out: dict[str, str] = {}
    for rec in (r.stdout or "").split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        h, _, note = rec.partition("\x1f")
        note = note.strip()
        if note:
            out[h.strip()] = note
    return out


def all_tags(repo: GitRepo) -> dict[str, list[str]]:
    """一次取所有 里程碑(tag)→版本 映射(避免每版 spawn)。
    set_tag 用轻量 tag 直接指 commit,故 %(objectname) 即版本 id。"""
    r = _git(repo, "for-each-ref", "--format=%(objectname) %(refname:short)",
             "refs/tags", check=False)
    out: dict[str, list[str]] = {}
    for line in (r.stdout or "").splitlines():
        obj, _, name = line.partition(" ")
        if obj.strip() and name.strip():
            out.setdefault(obj.strip(), []).append(name.strip())
    return out


def set_tag(repo: GitRepo, commit_id: str, name: str) -> None:
    _git(repo, "tag", "-f", name, commit_id)


def remove_tag(repo: GitRepo, name: str) -> None:
    # 删里程碑标签 != 删版本(INV-1):只摘掉这个名字,版本/历史/文件全留。幂等(已不存在不报错)。
    _git(repo, "tag", "-d", name, check=False)


def tags_for(repo: GitRepo, commit_id: str) -> list[str]:
    r = _git(repo, "tag", "--points-at", commit_id)
    return [t for t in r.stdout.splitlines() if t.strip()]
