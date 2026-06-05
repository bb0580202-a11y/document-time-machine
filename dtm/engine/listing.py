"""把历史整理成给用户看的行：相对时间 + 改动摘要 + 里程碑 + 备注。无 git 术语。"""
from __future__ import annotations

from dataclasses import dataclass

from .repo import GitRepo
from .messages import parse_message, humanize_time
from .backup import _DTM_OWN_FILES
from . import meta


@dataclass
class VersionRow:
    version_id: str        # 对用户用短 id
    when: str              # 相对时间
    summary: str           # 改了哪个文件、变大变小
    milestones: list[str]
    note: str


@dataclass
class ChangedFile:
    name: str
    delta_sign: str        # up | down | flat(相对父版的体积方向)


def changed_files(repo: GitRepo, commit_id: str) -> list[ChangedFile]:
    """这一版改动的用户文件 + 每个文件相对父版的体积方向(▲▼)。
    隐藏 dtm 自有簿记(.gitignore)。靠 blob 大小算方向,不用 numstat(二进制会坏)。"""
    out = []
    for name in repo.files_changed(commit_id):
        if name in _DTM_OWN_FILES:
            continue
        cur = repo.blob_size(commit_id, name)
        par = repo.blob_size(commit_id + "^", name)
        if cur is None:            # 该版已无(被删)→ 体积减为零
            sign = "down"
        elif par is None:          # 父版无(新增/首版)→ 从无到有
            sign = "up"
        elif cur > par:
            sign = "up"
        elif cur < par:
            sign = "down"
        else:
            sign = "flat"
        out.append(ChangedFile(name, sign))
    return out


def changed_files_batch(commit_id: str, files: list[str],
                        sizes: dict[str, int]) -> list[ChangedFile]:
    """批量版 changed_files:从预取的文件清单 + blob 大小算 ▲▼,不再每文件 spawn(治卡顿)。
    sizes={'<rev>:<path>': 字节数}(repo.batch_blob_sizes 一次取),缺=None。逻辑与 changed_files 一致。"""
    out = []
    for name in files:
        if name in _DTM_OWN_FILES:
            continue
        cur = sizes.get(f"{commit_id}:{name}")
        par = sizes.get(f"{commit_id}^:{name}")
        if cur is None:
            sign = "down"
        elif par is None:
            sign = "up"
        elif cur > par:
            sign = "up"
        elif cur < par:
            sign = "down"
        else:
            sign = "flat"
        out.append(ChangedFile(name, sign))
    return out


def build_version_list(repo: GitRepo) -> list[VersionRow]:
    rows = []
    for e in repo.log():
        parsed = parse_message(e.message)
        rows.append(VersionRow(
            version_id=e.commit_id[:8],
            when=humanize_time(e.unix_time),
            summary=parsed["summary"],
            milestones=meta.tags_for(repo, e.commit_id),
            note=meta.get_note(repo, e.commit_id),
        ))
    return rows
