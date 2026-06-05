from pathlib import Path

from dtm.engine.repo import GitRepo
from dtm.engine import backup
import dtm.engine.watcher as watcher_mod
from dtm.engine.watcher import DebouncedBackup, is_ignored_path


def test_debounce_coalesces_bursts(folder, make_docx_factory):
    repo = GitRepo(folder)
    repo.init()
    (folder / ".gitignore").write_text(backup.gitignore_text())
    calls = []
    db = DebouncedBackup(
        repo, folder, debounce=0.2,
        on_backup=lambda r: calls.append(r),
    )
    make_docx_factory(folder / "正文.docx", "A")
    for _ in range(5):           # 连续 5 次"变化"
        db.notify()
    db.flush_and_wait(timeout=2)  # 等去抖触发
    assert len(calls) == 1        # 5 次合并成 1 次备份
    assert calls[0].committed is True


def test_git_dir_changes_ignored(folder):
    repo = GitRepo(folder)
    repo.init()
    assert is_ignored_path(folder / ".git" / "index", folder) is True
    assert is_ignored_path(folder / "正文.docx", folder) is False


# ---- (a) 自动备份必须持跨进程 RepoLock（守护备份 vs GUI 还原同仓并发，git 不允许并发 index 操作）----
def test_fire_runs_backup_under_repolock(folder, monkeypatch):
    repo = GitRepo(folder)
    repo.init()
    db = DebouncedBackup(repo, folder)
    dtmlock = folder / ".git" / "dtm.lock"
    seen = {}

    def fake_backup(r, fld, source="auto"):
        seen["held"] = dtmlock.exists()    # 备份运行时 dtm.lock 在 = 跑在 RepoLock 内
        return backup.BackupResult(committed=False)

    monkeypatch.setattr(watcher_mod, "do_backup", fake_backup)
    db._fire()
    assert seen["held"] is True            # 自动备份持锁
    assert not dtmlock.exists()            # _fire 退出后释放
    db._done.wait(0)                       # _done 已置（即便失败也置，flush 不挂）


def test_fire_logs_and_survives_backup_failure(folder, monkeypatch, caplog):
    # INV-5:坏仓/锁忙导致备份失败→响亮记日志、不抛不挂(否则用户以为还被保护)
    import logging
    from dtm.engine.errors import DtmError
    repo = GitRepo(folder); repo.init()
    db = DebouncedBackup(repo, folder)

    def boom(r, fld, source="auto"):
        raise DtmError("commit 失败:仓库损坏")

    monkeypatch.setattr(watcher_mod, "do_backup", boom)
    with caplog.at_level(logging.ERROR):
        db._fire()                         # 不抛
    assert db._done.is_set()               # _done 仍置位,flush 不挂
    assert any("备份失败" in r.getMessage() for r in caplog.records)   # 响亮记了,没静默
