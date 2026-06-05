"""监听层。核心理念：事件=脏标记，去抖后 git add -A 扫真实状态（应对 Office 换名保存）。"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

from ..config import DEBOUNCE_SECONDS, FALLBACK_INTERVAL
from .repo import GitRepo
from .backup import do_backup
from .lock import RepoLock

# 云/网络同步目录名（启发式）：命中则降级轮询
_CLOUD_HINTS = ("OneDrive", "iCloud", "Dropbox", "Google Drive", "坚果云", "Nutstore")


def is_ignored_path(path: Path, folder: Path) -> bool:
    try:
        rel = Path(path).resolve().relative_to(Path(folder).resolve())
    except ValueError:
        return True
    return ".git" in rel.parts


def looks_like_cloud(folder: Path) -> bool:
    s = str(Path(folder).resolve())
    return any(h.lower() in s.lower() for h in _CLOUD_HINTS)


class DebouncedBackup:
    """合并突发事件：最后一次变化后静默 `debounce` 秒才备份一次。串行锁防并发。"""

    def __init__(self, repo: GitRepo, folder: Path, debounce=DEBOUNCE_SECONDS, on_backup=None):
        self.repo, self.folder = repo, Path(folder)
        self.debounce = debounce
        self.on_backup = on_backup or (lambda r: None)
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()      # 串行化备份，禁并发 git
        self._done = threading.Event()

    def notify(self) -> None:
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._done.clear()
            self._timer = threading.Timer(self.debounce, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        # 嵌套顺序固定:进程内 threading.Lock 在外、跨进程 RepoLock 在内(GUI 是另一进程、
        # 只拿 RepoLock,无跨锁环)。RepoLock 串行化守护备份 vs GUI 还原,git 禁同仓并发 index 操作。
        with self._lock:
            try:
                with RepoLock(self.folder):
                    result = do_backup(self.repo, self.folder, source="auto")
                self.on_backup(result)
            except Exception:
                # INV-5 失败响亮:坏仓/锁忙导致备份失败别静默吞(否则用户以为还被保护着)。
                # 记进 dtm.log;不重抛(避免 Timer 线程死掉),兜底轮询会重试。
                logging.exception("自动备份失败(%s)——本次未受保护,可能仓库损坏或锁忙", self.folder)
            finally:
                self._done.set()   # 即便失败也置位,flush_and_wait 不挂

    def flush_and_wait(self, timeout=None) -> None:
        self._done.wait(timeout)

    def cancel(self) -> None:
        with self._lock:
            if self._timer:
                self._timer.cancel()


class _Handler(FileSystemEventHandler):
    def __init__(self, db: DebouncedBackup, folder: Path):
        self.db, self.folder = db, folder

    def on_any_event(self, event):
        if is_ignored_path(Path(event.src_path), self.folder):
            return
        self.db.notify()       # 任何事件都只当脏标记


def make_observer(folder: Path):
    """云/网络盘用 PollingObserver（watchdog 官方建议），否则原生事件。"""
    return PollingObserver() if looks_like_cloud(folder) else Observer()


def watch(repo: GitRepo, folder: Path, on_backup=None, on_status=None):
    """前台监听（Phase 1）。Phase 2 再包成守护进程。"""
    folder = Path(folder)
    db = DebouncedBackup(repo, folder, on_backup=on_backup)
    observer = make_observer(folder)
    observer.schedule(_Handler(db, folder), str(folder), recursive=True)
    observer.start()
    # 定时兜底：即使事件漏报，周期性 git add -A 检查一次（FALLBACK_INTERVAL）
    stop = threading.Event()

    def _fallback():
        while not stop.wait(FALLBACK_INTERVAL):
            db.notify()

    fb = threading.Thread(target=_fallback, daemon=True)
    fb.start()
    return observer, db, stop   # 调用方负责 observer.stop()/join() 与 stop.set()
