"""GUI 与 engine 之间的薄桥:只做参数转译 + 调 engine + 返回 JSON 可序列化结构。
绝不写业务逻辑(逻辑在 engine)。写操作抢 RepoLock(跨进程串行)。"""
from __future__ import annotations
import functools
import json
import logging
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
import webview
from ..engine.repo import GitRepo
from ..engine import registry, treemap, backup, identity, meta, restore, integrity, listing, health, probe, flags
from ..engine.messages import parse_message, humanize_time
from ..engine.lock import RepoLock
from ..engine.errors import DtmError
from ..engine.treemap import treemap_to_dict, _delta_sign
from ..engine.autostart import get_autostart as _autostart_backend  # 别名避与 bridge.get_autostart 自遮蔽
from .runtime import daemon_launch_command

# 兜底人话(INV-5/6):非 DtmError 的技术异常绝不原样漏给用户。
_GENERIC_ERROR = "操作没完成，请再试一次；若反复出现，重启一下时光机。"


def _humanize(fn):
    """bridge 公开方法的错误收口:DtmError(已人话)原样上抛;其它任何异常吞掉技术细节、
    换人话给用户,原始异常 logging.exception 打到守护终端供排查(不糊用户脸)。"""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except DtmError:
            raise
        except Exception as e:
            logging.exception("bridge %s 失败", fn.__name__)
            raise DtmError(_GENERIC_ERROR) from e
    return wrapper


def _humanize_all(cls):
    """给 Bridge 所有公开方法统一套 _humanize(DRY、单处);无论 pywebview 怎么解析方法都拿到包好的版本。"""
    for name, attr in list(vars(cls).items()):
        if callable(attr) and not name.startswith("_"):
            setattr(cls, name, _humanize(attr))
    return cls


@_humanize_all
class Bridge:
    def __init__(self, store: Path | None = None, search_roots: list[Path] | None = None):
        self.store = Path(store) if store else registry.default_store()
        # 默认不扫家目录:list_folders 对路径失效的库(pending)若递归扫 ~/找 UUID,Windows 上每次卡 7-10 秒
        # (开窗/归档后刷新/切库都调 list_folders=每次都卡)。搬走的库改由"找回"显式动作扫,不在热路径。
        self.search_roots = search_roots if search_roots is not None else []

    # ---------- 读 ----------
    def pick_folder(self) -> str | None:
        """弹原生选目录框(只允许选文件夹),返回选中路径或 None(取消)。
        唯一碰窗口对象处,必须在 GUI 进程跑(Bridge 正在 GUI 进程)。不合成 pick_and_add:
        保 add_folder 纯净可单测;此为不可单测的 UI 触点,单独隔离,靠 CP 验。"""
        if not webview.windows:
            return None
        result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else str(result)

    def reveal_path(self, path: str) -> None:
        """在系统文件管理器里打开/定位一个路径(UI 触点,纯副作用、不碰 engine/repo,无需 RepoLock)。
        目录→打开该文件夹;文件→在文件管理器里选中它。一个方法同时服务"前往库"与"还原后定位副本"。
        macOS=open/-R;Windows=explorer(/select 选中文件)。"""
        p = Path(path)
        if not p.exists():
            raise DtmError("找不到这个位置，它可能已被移动或删除。")
        if sys.platform == "darwin":
            args = ["open", str(p)] if p.is_dir() else ["open", "-R", str(p)]
            subprocess.run(args, check=False)
        elif sys.platform == "win32":
            # 目录→explorer 打开;文件→/select 打开父目录并选中它。explorer 常返回非0,check=False。
            args = ["explorer", str(p)] if p.is_dir() else ["explorer", f"/select,{p}"]
            subprocess.run(args, check=False)

    def list_folders(self) -> list[dict]:
        folders = registry.resolve(self.store, self.search_roots)
        # GUI 是唯一写者:resolve 找回的路径/status 若与磁盘不同,显式回写持久化。
        # 仅在真有变化时写,避免无谓触发守护的 folders.json reconcile。
        if [asdict(f) for f in folders] != [asdict(f) for f in registry.load(self.store)]:
            registry.save(self.store, folders)
        return [{**asdict(f), "name": Path(f.path).name} for f in folders]

    def check_downtime(self) -> dict:
        """裸奔回看(盲区5):守护上次有没有没打招呼就停过?有则返回空窗秒数,GUI 弹黄条提醒。"""
        try:
            data = json.loads((self.store.parent / "downtime.json").read_text())
            return {"gap_seconds": data["gap"]}
        except (OSError, ValueError, KeyError):
            return {}

    def ack_downtime(self) -> None:
        """用户点"知道了":清掉空窗记录,别再提醒。"""
        try:
            (self.store.parent / "downtime.json").unlink()
        except OSError:
            pass

    def check_health(self, folder: str) -> dict:
        """仓库自检结果给 GUI:坏了前端亮红横幅(小白可靠看到的告警面)。便宜检查、不修复。
        叠加守护后台深度体检(fsck)的结论:HEAD 坏更紧急、优先;HEAD 好再看 fsck 有没有
        逮到历史深处坏块(守护写 .git/dtm_fsck.json,这里只读,不在开窗热路径跑 fsck)。"""
        ok, reason = health.check_repo(GitRepo(folder))
        if not ok:
            return {"ok": ok, "reason": reason}
        try:
            data = json.loads((Path(folder) / ".git" / "dtm_fsck.json").read_text(encoding="utf-8"))
            if not data.get("ok", True):
                return {"ok": False, "reason": data.get("reason") or ""}
        except (OSError, ValueError):
            pass
        return {"ok": True, "reason": ""}

    def get_treemap(self, folder: str) -> dict:
      with probe.profile("get_treemap"):
        repo = GitRepo(folder)
        tm = treemap.from_repo(repo, current_id=repo.head())   # CP-3:真 HEAD
        return treemap_to_dict(tm)

    def peek(self, folder: str) -> dict:
        """轻量版本指纹:给 GUI 轮询用,变了才整体刷新(HEAD 动/版本数变都侦测得到)。"""
        with probe.profile("peek"):   # peek 每 4s 轮询,也计入探针看轮询开销
            repo = GitRepo(folder)
            return {"head": repo.head(), "count": len(repo.log("--branches"))}

    def get_album(self, folder: str) -> list[dict]:
      with probe.profile("get_album"):
        repo = GitRepo(folder)
        # 批量取代每版 spawn(治 Windows 卡顿):head/notes/tags/文件清单各一次,blob 大小一次批量问。
        head = repo.head()
        notes = meta.all_notes(repo)
        tags = meta.all_tags(repo)
        corrupt = flags.corrupt_map(repo)   # {版本: [可能损坏的文件]}，备份时记的持久标记
        files_map = repo.changed_files_map()
        specs = [f"{cid}{suf}:{name}"
                 for cid, files in files_map.items() for name in files
                 for suf in ("", "^")]
        sizes = repo.batch_blob_sizes(specs)
        cards = []
        for e in repo.log("--branches"):
            parsed = parse_message(e.message)
            note = notes.get(e.commit_id, "")
            abs_minute = e.iso_time[:16].replace("T", " ")
            cards.append({
                "version_id": e.commit_id[:8],
                "full_id": e.commit_id,
                "title": note or abs_minute,
                "abs_minute": abs_minute,
                "abs_seconds": e.iso_time[:19].replace("T", " "),
                "relative": humanize_time(e.unix_time),
                "note": note,
                "milestones": tags.get(e.commit_id, []),
                "delta_sign": _delta_sign(parsed["summary"]),
                "summary": parsed["summary"],
                "files": [asdict(c) for c in
                          listing.changed_files_batch(e.commit_id,
                                                      files_map.get(e.commit_id, []), sizes)],
                "is_current": e.commit_id == head,
                "corrupt_files": corrupt.get(e.commit_id, []),   # 这一版可能损坏的文件→相册显 ⚠
            })
        cards.sort(key=lambda c: c["abs_seconds"], reverse=True)   # 最新在前
        return cards

    # ---------- 写(都抢 RepoLock 串行,跨进程安全) ----------
    def add_folder(self, folder: str) -> dict:
        folder = Path(folder)
        repo = GitRepo(folder)
        if not repo.is_repo():                       # 未守护→开启守护(init+首备)
            repo.init(); identity.write_identity(folder)
            (folder / ".gitignore").write_text(backup.gitignore_text())
            with RepoLock(folder):                   # 首备也持锁,与守护自动备份同串行(防并发抢 index.lock)
                backup.do_backup(repo, folder, source="auto")
        elif not (folder / ".git" / identity.IDENTITY_FILE).exists():
            identity.write_identity(folder)
        entry = registry.add(self.store, folder)
        return {**asdict(entry), "name": folder.name}

    def remove_folder(self, uuid: str) -> None:
        registry.remove(self.store, uuid)            # 只移出清单,绝不删历史(INV-1)

    def _folder_by_uuid(self, uuid: str) -> str:
        f = next((x for x in registry.load(self.store) if x.uuid == uuid), None)
        if f is None:
            raise DtmError("找不到这个文件夹。")
        return f.path

    def archive_folder(self, uuid: str) -> None:
        # 归档:flush 封存"归档那刻的样子"(兜住去抖窗口里没备的编辑)→ 写 archived=true,
        # 守护 reconcile 据此停 watcher 但留列表。flush 抢 RepoLock 与 watcher 自动备份串行(靠 #1 修复)。
        folder = self._folder_by_uuid(uuid)
        with RepoLock(folder):
            backup.do_backup(GitRepo(folder), Path(folder))
        registry.set_archived(self.store, uuid, True)

    def resume_folder(self, uuid: str) -> None:
        # 继续记录:先补拍一版基线(归档期无保护的改动落历史、不留空洞)→ 再 archived=false 重启看管。
        # 顺序焊死:补拍在 archived 仍 true、watcher 未起时做,基线不与重启的 watcher race。
        folder = self._folder_by_uuid(uuid)
        with RepoLock(folder):
            backup.do_backup(GitRepo(folder), Path(folder))
        registry.set_archived(self.store, uuid, False)

    def restore(self, folder: str, version_id: str, rel_path: str) -> dict:
        repo = GitRepo(folder)
        with RepoLock(folder):
            r = restore.safe_restore(repo, Path(folder), version_id, rel_path)
        return {"restored_path": r.restored_path, "pre_restore": r.pre_restore_commit}

    def restore_version(self, folder: str, version_id: str) -> dict:
        repo = GitRepo(folder)
        with RepoLock(folder):
            r = restore.restore_version(repo, Path(folder), version_id)
        return {"restored_paths": r.restored_paths, "pre_restore": r.pre_restore_commit}

    def set_note(self, folder: str, version_id: str, text: str) -> None:
        repo = GitRepo(folder)
        with RepoLock(folder):
            meta.set_note(repo, version_id, text)

    def set_tag(self, folder: str, version_id: str, name: str) -> None:
        repo = GitRepo(folder)
        with RepoLock(folder):
            meta.set_tag(repo, version_id, name)

    def remove_tag(self, folder: str, name: str) -> None:
        # 删里程碑标签:可逆(撤销=重新 set_tag),只摘名字不动版本(INV-1)。删备注走 set_note(id,"")。
        repo = GitRepo(folder)
        with RepoLock(folder):
            meta.remove_tag(repo, name)

    def get_autostart(self) -> bool:
        # is_enabled = plist 文件存在(不靠 launchctl 加载态)→ 开开关后即便没重登录,回显也不弹回 OFF
        return _autostart_backend().is_enabled()

    def set_autostart(self, on: bool) -> None:
        # 只装不 load-now:开=写 plist(下次开机由 launchd 加载),关=bootout 上次实例+删 plist。
        # 不杀当前进程内守护(关开关只停自启)。失败抛 DtmError,经 _humanize_all 上抛 toast。
        a = _autostart_backend()
        if on:
            a.install(daemon_launch_command())
        else:
            a.uninstall()

    def create_branch(self, folder: str, version_id: str, name: str) -> None:
        repo = GitRepo(folder)
        with RepoLock(folder):
            repo.create_branch(name, version_id)

    def verify(self, folder: str, rel_path: str) -> dict:
        ok, reason = integrity.check(Path(folder) / rel_path)
        return {"ok": ok, "reason": reason}
