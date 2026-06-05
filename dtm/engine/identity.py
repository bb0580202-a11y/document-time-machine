"""仓库身份证：写在 .git/dtm_identity.json，搬家后靠 UUID 重新认领。"""
from __future__ import annotations

import json
import uuid
import datetime
from pathlib import Path

from ..config import IDENTITY_FILE, TOOL_MARKER
from .errors import NotADtmFolderError


def _path(folder: Path) -> Path:
    return Path(folder) / ".git" / IDENTITY_FILE


def write_identity(folder: Path) -> dict:
    data = {
        "uuid": uuid.uuid4().hex,
        "created_at": datetime.datetime.now().astimezone().isoformat(),
        "created_by": TOOL_MARKER,
    }
    _path(folder).write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return data


def read_identity(folder: Path) -> dict:
    p = _path(folder)
    if not p.exists():
        raise NotADtmFolderError(
            "这个文件夹还没有开启版本守护（找不到守护标记）。"
        )
    return json.loads(p.read_text())


def find_repo_by_uuid(target_uuid: str, search_roots: list[Path], max_depth: int = 4):
    """在常见位置扫带身份证的 .git，找 UUID 匹配的文件夹。"""
    for root in search_roots:
        root = Path(root)
        if not root.exists():
            continue
        for ident in root.rglob(f".git/{IDENTITY_FILE}"):
            try:
                if json.loads(ident.read_text()).get("uuid") == target_uuid:
                    return ident.parent.parent
            except (OSError, ValueError):
                continue
    return None
