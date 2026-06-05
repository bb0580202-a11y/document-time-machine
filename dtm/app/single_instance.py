"""守护单实例守卫:独占 config/daemon.lock。

进程亡→内核自动释锁(无 stale,区别于 RepoLock 的 create-file+超时那套)。
⚠️ acquire 返回的 fd 必须被进程全程持有(挂 Daemon._inst_fd):
   fd 被 GC/close → 锁释放 → 守卫失效。见 test_single_instance 反向用例。

跨平台:POSIX(Mac/Linux) 用 fcntl.flock;Windows 无 fcntl,用 msvcrt.locking
锁文件首字节。两者语义同:内核级建议锁、非阻塞、进程退出自动释、返回值仍是
同一个 fd(接口不变)。Windows 分支只能真机 CP 验(Mac 无 msvcrt)。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.platform == "win32":
    import msvcrt

    def _try_lock_nb(fd: int) -> None:
        """非阻塞锁文件首字节;已被占→抛 OSError(PermissionError)。"""
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
else:
    import fcntl

    def _try_lock_nb(fd: int) -> None:
        """非阻塞独占整文件;已被占→抛 BlockingIOError(OSError 子类)。"""
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def acquire(lock_path: Path) -> int | None:
    """拿到独占锁→返回 fd(调用方必须全程持有、绝不关);已被占→None。"""
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)  # py3 默认 non-inheritable
    try:
        _try_lock_nb(fd)
    except OSError:        # flock→BlockingIOError / msvcrt→PermissionError,皆 OSError 子类
        os.close(fd)
        return None
    return fd
