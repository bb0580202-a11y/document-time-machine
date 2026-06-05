"""按仓库的跨进程串行锁。锁文件 .git/dtm.lock 记 {pid,host,ts}。
守护进程的备份与 GUI 子进程的写操作跑 git 前都先抢这把锁，串行化避免抢 .git/index.lock。
崩溃残留(stale)的锁靠"超时 + 同主机 pid 已死"自动夺取，绝不让 GUI 永久卡死。"""
from __future__ import annotations
import json
import os
import socket
import sys
import time
from pathlib import Path
from .errors import LockBusyError

_HOST = socket.gethostname()


def _pid_alive_win(pid: int) -> bool:
    """Windows 探活:os.kill(pid,0) 在 Windows 会走 TerminateProcess 真把进程杀掉(不是探测!)
    → 改用 OpenProcess+GetExitCodeProcess。偏保守:查不到当活着,宁可不夺活进程的锁。"""
    if pid <= 0:
        return False
    import ctypes
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False  # 打不开 → 进程不存在,残留锁可夺
    try:
        code = ctypes.c_ulong()
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return code.value == STILL_ACTIVE  # 259=仍在跑(已退出会是真实退出码)
        return True   # 查不到退出码 → 保守当活着,不误夺活进程的锁
    finally:
        kernel32.CloseHandle(handle)


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        return _pid_alive_win(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 进程存在，只是不是我们能发信号的
    except (OSError, ValueError):
        return False
    return True


class RepoLock:
    def __init__(self, folder, stale_after: float = 30.0,
                 acquire_timeout: float = 10.0, poll: float = 0.1,
                 index_lock_stale_after: float = 10.0):
        self.path = Path(folder) / ".git" / "dtm.lock"
        self.stale_after = stale_after
        self.acquire_timeout = acquire_timeout
        self.poll = poll
        self.index_lock_stale_after = index_lock_stale_after
        self._held = False

    def _clear_stale_index_lock(self) -> None:
        """拿到 dtm.lock 后调：此刻仍在的 git `.git/index.lock` 只能是崩溃残留——
        所有写 index 的 git 操作都先抢这把锁(见模块 docstring)，故没有别的 dtm 进程在跑 git。
        仅清老化(>index_lock_stale_after 秒)的，防误删极罕见的外部手动 git 在途锁。
        不清残留 → 断电/崩溃后下次 git 操作会卡"another git process running"。"""
        idx = self.path.parent / "index.lock"        # .git/index.lock
        try:
            age = time.time() - idx.stat().st_mtime
        except OSError:
            return                                    # 不存在/读不了 → 无需清
        if age >= self.index_lock_stale_after:
            try:
                idx.unlink()
            except OSError:
                pass

    def _payload(self) -> bytes:
        return json.dumps(
            {"pid": os.getpid(), "host": _HOST, "ts": time.time()}
        ).encode()

    def _try_create(self) -> bool:
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        try:
            os.write(fd, self._payload())
        finally:
            os.close(fd)
        return True

    def _is_stale(self) -> bool:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return True  # 读不了/内容坏了 → 当残留
        if time.time() - data.get("ts", 0) < self.stale_after:
            return False  # 还新鲜，不能抢
        # 已超时：同主机才能查 pid；不同主机无从判断，只认超时(判 stale)
        if data.get("host") == _HOST and _pid_alive(int(data.get("pid", -1))):
            return False
        return True

    def acquire(self) -> "RepoLock":
        deadline = time.time() + self.acquire_timeout
        while True:
            if self._try_create():
                self._held = True
                self._clear_stale_index_lock()   # 持锁即清崩溃残留的 git index.lock
                return self
            if self._is_stale():
                try:
                    self.path.unlink()
                except OSError:
                    pass
                continue
            if time.time() >= deadline:
                raise LockBusyError("另一个备份正在进行，请稍候再试。")
            time.sleep(self.poll)

    def release(self) -> None:
        if self._held:
            try:
                self.path.unlink()
            except OSError:
                pass
            self._held = False

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
