import threading
from pathlib import Path
import dtm.app.daemon as daemon_mod
from dtm.app.daemon import Daemon
from dtm.engine import registry, identity
from dtm.engine.repo import GitRepo


class _FakeObserver:
    def __init__(self): self.stopped = False
    def stop(self): self.stopped = True
    def join(self): pass


class _FakeDb:
    def cancel(self): pass


def _fake_watch(repo, folder, *a, **k):
    return _FakeObserver(), _FakeDb(), threading.Event()


def _guard(folder):
    GitRepo(folder).init(); identity.write_identity(folder)


def test_reconcile_starts_active_folders(tmp_path, monkeypatch):
    monkeypatch.setenv("DTM_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(daemon_mod, "watch", _fake_watch)
    f1 = tmp_path / "p1"; f1.mkdir(); _guard(f1)
    store = registry.default_store()
    registry.add(store, f1)
    d = Daemon()
    d.reconcile()
    uuid1 = identity.read_identity(f1)["uuid"]
    assert set(d.running.keys()) == {uuid1}


def test_reconcile_stops_removed_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("DTM_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(daemon_mod, "watch", _fake_watch)
    f1 = tmp_path / "p1"; f1.mkdir(); _guard(f1)
    store = registry.default_store()
    u1 = registry.add(store, f1).uuid
    d = Daemon()
    d.reconcile()
    registry.remove(store, u1)
    d.reconcile()
    assert d.running == {}


def test_start_config_watch_creates_missing_dir(tmp_path, monkeypatch):
    # 全新安装:config 目录不存在,起 config watch 不能崩
    cfg = tmp_path / "never_created"
    monkeypatch.setenv("DTM_CONFIG_DIR", str(cfg))
    monkeypatch.setattr(daemon_mod, "watch", _fake_watch)
    d = Daemon()
    d.start_config_watch()
    assert cfg.exists()                       # mkdir 兜住,目录被建出
    d.stop_config_watch()                     # 收尾,别留线程


def test_check_health_logs_warning_on_corrupt_repo(folder, monkeypatch, caplog):
    # #2:守护启动自检逮坏仓→响亮记进日志(给排查),不静默
    import logging
    monkeypatch.setenv("DTM_CONFIG_DIR", str(folder.parent / "cfg"))
    repo = GitRepo(folder); repo.init()
    (folder / "a.txt").write_text("x"); repo.add_all(); cid = repo.commit("m")
    (folder / ".git" / "objects" / cid[:2] / cid[2:]).unlink()   # 真造坏仓
    d = Daemon()
    with caplog.at_level(logging.WARNING):
        d._check_health(str(folder))
    assert any("损坏" in r.getMessage() for r in caplog.records)


def test_check_health_silent_on_healthy_repo(folder, monkeypatch, caplog):
    import logging
    monkeypatch.setenv("DTM_CONFIG_DIR", str(folder.parent / "cfg"))
    repo = GitRepo(folder); repo.init()
    (folder / "a.txt").write_text("x"); repo.add_all(); repo.commit("m")
    d = Daemon()
    with caplog.at_level(logging.WARNING):
        d._check_health(str(folder))
    assert not any("损坏" in r.getMessage() for r in caplog.records)   # 好仓安静


def test_detect_downtime_writes_record_on_unclean_gap(tmp_path, monkeypatch):
    # #3:上次没打招呼就断、空窗够久 → 记下空窗给 GUI 提醒
    import time, json
    monkeypatch.setenv("DTM_CONFIG_DIR", str(tmp_path / "cfg"))
    d = Daemon()
    d._beat_path.parent.mkdir(parents=True, exist_ok=True)
    d._beat_path.write_text(json.dumps({"ts": time.time() - 9999, "clean": False}))
    d.detect_downtime_on_start()
    assert d._downtime_path.exists()
    assert json.loads(d._downtime_path.read_text())["gap"] > 600


def test_detect_downtime_silent_on_clean_quit(tmp_path, monkeypatch):
    # 上次是干净退出(用户主动退) → 不误报裸奔
    import time, json
    monkeypatch.setenv("DTM_CONFIG_DIR", str(tmp_path / "cfg2"))
    d = Daemon()
    d._beat_path.parent.mkdir(parents=True, exist_ok=True)
    d._beat_path.write_text(json.dumps({"ts": time.time() - 9999, "clean": True}))
    d.detect_downtime_on_start()
    assert not d._downtime_path.exists()


def test_should_open_window_consumes_flag(tmp_path):
    # 叫醒开窗判据:有 flag→真+消费(删),无→假;幂等
    from dtm.app.daemon import should_open_window
    assert should_open_window(tmp_path) is False        # 无 flag
    (tmp_path / "open_window.req").touch()
    assert should_open_window(tmp_path) is True          # 有 flag→真
    assert not (tmp_path / "open_window.req").exists()   # 且被消费
    assert should_open_window(tmp_path) is False          # 再查→假


def test_reconcile_skips_archived_folder(tmp_path, monkeypatch):
    # 归档项不进 desired → watcher 不起;但仍留 folders.json 列表(与"移除"的结构差异)
    monkeypatch.setenv("DTM_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(daemon_mod, "watch", _fake_watch)
    f1 = tmp_path / "p1"; f1.mkdir(); _guard(f1)
    store = registry.default_store()
    u1 = registry.add(store, f1).uuid
    registry.set_archived(store, u1, True)
    d = Daemon()
    d.reconcile()
    assert u1 not in d.running                                  # watcher 没起
    assert any(f.uuid == u1 for f in registry.load(store))      # 仍留列表
