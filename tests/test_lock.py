import json
import os
import time
import pytest
from dtm.engine.lock import RepoLock, _HOST
from dtm.engine.errors import LockBusyError


@pytest.fixture
def gitfolder(folder):
    (folder / ".git").mkdir()
    return folder


def test_acquire_creates_and_release_removes(gitfolder):
    lk = RepoLock(gitfolder)
    lk.acquire()
    assert (gitfolder / ".git" / "dtm.lock").exists()
    lk.release()
    assert not (gitfolder / ".git" / "dtm.lock").exists()


def test_context_manager(gitfolder):
    with RepoLock(gitfolder):
        assert (gitfolder / ".git" / "dtm.lock").exists()
    assert not (gitfolder / ".git" / "dtm.lock").exists()


def test_second_acquire_blocks_when_fresh(gitfolder):
    held = RepoLock(gitfolder).acquire()
    try:
        with pytest.raises(LockBusyError):
            RepoLock(gitfolder, acquire_timeout=0.3, poll=0.05).acquire()
    finally:
        held.release()


def test_stale_lock_is_stolen(gitfolder):
    # 残留锁：同主机 + 旧时间戳 + 几乎不可能存活的 pid → 判 stale，应被夺取
    (gitfolder / ".git" / "dtm.lock").write_text(
        json.dumps({"pid": 2**31 - 1, "host": _HOST, "ts": time.time() - 9999})
    )
    lk = RepoLock(gitfolder, acquire_timeout=1.0)
    lk.acquire()
    assert lk._held is True
    lk.release()


# ---- (b) 持 RepoLock 时清崩溃残留的 git index.lock（防崩后卡死“another git process running”）----
def test_stale_index_lock_cleared_on_acquire(gitfolder):
    # 老化的 .git/index.lock = 崩溃残留：持 dtm.lock 后没有别的 dtm 进程在跑 git，安全清。
    idx = gitfolder / ".git" / "index.lock"
    idx.write_text("")
    old = time.time() - 999
    os.utime(idx, (old, old))
    with RepoLock(gitfolder, index_lock_stale_after=10.0):
        assert not idx.exists()            # 一拿到锁就清掉残留


def test_fresh_index_lock_kept_on_acquire(gitfolder):
    # 新鲜的 index.lock（极罕见：外部手动 git 刚建）不误删——只清老化的。
    idx = gitfolder / ".git" / "index.lock"
    idx.write_text("")
    with RepoLock(gitfolder, index_lock_stale_after=10.0):
        assert idx.exists()
    idx.unlink()
