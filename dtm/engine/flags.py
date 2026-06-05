"""「可能损坏的版本」标记：dtm 自有簿记，落在 .git/dtm_corrupt.json（随文件夹搬家）。

备份那刻若某版某文件完整性自检没过（Office/PDF 打不开），记下 {版本: [坏文件]}。
→ 相册卡片显 ⚠、还原时提醒用户避开（坏的是源文件本身，我们修不了，只能如实标出来）。
只读/只加，绝不碰用户文件或历史快照（贴 INV-1 边，纯旁路簿记）。
"""
from __future__ import annotations

import json
from pathlib import Path

from .repo import GitRepo

_FILE = "dtm_corrupt.json"


def _path(repo: GitRepo) -> Path:
    return repo.folder / ".git" / _FILE


def corrupt_map(repo: GitRepo) -> dict[str, list[str]]:
    """返回 {完整版本id: [这一版里可能损坏的文件名]}。读不到/坏了 → 空（绝不因此崩）。"""
    try:
        data = json.loads(_path(repo).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: list(v) for k, v in data.items() if isinstance(v, list)}


def record_corrupt(repo: GitRepo, commit_id: str, files: list[str]) -> None:
    """把这一版检出来可能损坏的文件并入簿记（去重、累积）。原子落盘，失败静默（簿记非关键路径）。"""
    if not files:
        return
    m = corrupt_map(repo)
    have = set(m.get(commit_id, []))
    have.update(files)
    m[commit_id] = sorted(have)
    p = _path(repo)
    tmp = p.with_name(p.name + ".tmp")
    try:
        tmp.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)   # 原子替换
    except OSError:
        pass
