"""全局"被守护文件夹清单"。存 {path,uuid,added_at,status}。
开机用 resolve()：路径失效就用 Phase 1 的 UUID 身份证自愈(搬家找回)；
找不到则标 status=pending(界面提示"待指认")。逻辑纯，不进 GUI 层。"""
from __future__ import annotations
import datetime
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from . import identity


@dataclass
class Folder:
    path: str
    uuid: str
    added_at: str
    status: str = "active"  # active | pending（派生量,resolve 算）
    archived: bool = False  # 用户意图:停止看管但留列表(GUI 唯一写、持久;与 status 分层)


def default_store() -> Path:
    """全局清单文件位置(跨平台)。DTM_CONFIG_DIR 可覆盖(测试/便携用)。"""
    base = os.environ.get("DTM_CONFIG_DIR")
    if base:
        root = Path(base)
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "doc-time-machine"
    elif sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", str(Path.home()))) / "doc-time-machine"
    else:
        root = Path.home() / ".config" / "doc-time-machine"
    return root / "folders.json"


def load(store: Path) -> list[Folder]:
    store = Path(store)
    if not store.exists():
        return []
    return [Folder(**f) for f in json.loads(store.read_text())]


def save(store: Path, folders: list[Folder]) -> None:
    store = Path(store)
    store.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps([asdict(f) for f in folders], ensure_ascii=False, indent=2)
    # 原子写:同目录 temp 写满再 os.replace 换名(同文件系统保证 replace 原子);
    # 防守护读到半截 JSON。temp 用唯一名,避免并发覆盖彼此的 temp。
    tmp = store.parent / f".{store.name}.{os.getpid()}.tmp"
    tmp.write_text(payload)
    os.replace(tmp, store)


def add(store: Path, folder_path) -> Folder:
    folder_path = Path(folder_path)
    ident = identity.read_identity(folder_path)  # 未 init 会抛 NotADtmFolderError
    folders = [f for f in load(store) if f.uuid != ident["uuid"]]  # 去重
    entry = Folder(
        path=str(folder_path.resolve()),
        uuid=ident["uuid"],
        added_at=datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        status="active",
    )
    folders.append(entry)
    save(store, folders)
    return entry


def remove(store: Path, target_uuid: str) -> None:
    save(store, [f for f in load(store) if f.uuid != target_uuid])


def set_archived(store: Path, target_uuid: str, archived: bool) -> None:
    """改归档意图(GUI 唯一写)。只动 archived,不删项、不碰历史(INV-1)。"""
    folders = load(store)
    for f in folders:
        if f.uuid == target_uuid:
            f.archived = archived
    save(store, folders)


def resolve(store: Path, search_roots: list[Path]) -> list[Folder]:
    """纯查询:算每项的 status + UUID 解析到的当前路径,返回 in-memory 列表,永不写盘。
    持久化(把找回的路径落回 folders.json)是调用方(GUI 唯一写者)的事:resolve(...) 后显式 save。
    守护只 resolve 用完即弃——结构保证「守护永不写 folders.json」。"""
    folders = load(store)
    for f in folders:
        p = Path(f.path)
        if p.exists() and (p / ".git").is_dir():
            f.status = "active"
            continue
        found = identity.find_repo_by_uuid(f.uuid, search_roots)
        if found is not None:
            f.path = str(Path(found).resolve())
            f.status = "active"
        else:
            f.status = "pending"
    return folders
