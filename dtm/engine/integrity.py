"""完整性自检：zip 系 Office 验 zip 可打开；pdf 验头尾标记；其它跳过。"""
from __future__ import annotations

import zipfile
from pathlib import Path

from ..config import ZIP_OFFICE_EXTS


def check(path: Path) -> tuple[bool, str]:
    path = Path(path)
    ext = path.suffix.lower()
    if ext in ZIP_OFFICE_EXTS:
        try:
            with zipfile.ZipFile(path) as z:
                if z.testzip() is not None:
                    return False, f"{path.name} 似乎损坏（内部数据校验未通过）"
            return True, ""
        except (zipfile.BadZipFile, OSError):
            return False, f"{path.name} 似乎损坏（无法作为文档打开）"
    if ext == ".pdf":
        try:
            data = path.read_bytes()
            if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-1024:]:
                return False, f"{path.name} 似乎损坏（PDF 头尾标记缺失）"
            return True, ""
        except OSError:
            return False, f"{path.name} 无法读取"
    return True, ""
