from pathlib import Path
from dtm.engine.repo import GitRepo
from dtm.engine import identity, registry


def _init(folder):
    GitRepo(folder).init()
    identity.write_identity(folder)


def test_add_persists_uuid(folder, tmp_path):
    store = tmp_path / "folders.json"
    _init(folder)
    entry = registry.add(store, folder)
    assert entry.status == "active"
    loaded = registry.load(store)
    assert len(loaded) == 1
    assert loaded[0].uuid == identity.read_identity(folder)["uuid"]


def test_add_dedupes_same_uuid(folder, tmp_path):
    store = tmp_path / "folders.json"
    _init(folder)
    registry.add(store, folder)
    registry.add(store, folder)
    assert len(registry.load(store)) == 1


def test_remove(folder, tmp_path):
    store = tmp_path / "folders.json"
    _init(folder)
    u = registry.add(store, folder).uuid
    registry.remove(store, u)
    assert registry.load(store) == []


def test_resolve_relocates_moved_folder(folder, tmp_path):
    store = tmp_path / "folders.json"
    _init(folder)
    registry.add(store, folder)
    moved = folder.parent / "renamed_thesis"
    folder.rename(moved)
    out = registry.resolve(store, [folder.parent])
    assert out[0].status == "active"
    assert Path(out[0].path) == moved.resolve()


def test_resolve_marks_pending_when_not_found(folder, tmp_path):
    store = tmp_path / "folders.json"
    _init(folder)
    registry.add(store, folder)
    moved = tmp_path / "elsewhere" / "gone"
    moved.parent.mkdir()
    folder.rename(moved)
    out = registry.resolve(store, [tmp_path / "nonexistent_root"])
    assert out[0].status == "pending"


def test_default_store_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("DTM_CONFIG_DIR", str(tmp_path))
    assert registry.default_store() == tmp_path / "folders.json"


def test_resolve_never_writes_disk(folder, tmp_path):
    store = tmp_path / "folders.json"
    _init(folder)
    registry.add(store, folder)
    before = store.read_bytes()
    moved = folder.parent / "renamed_thesis"
    folder.rename(moved)
    out = registry.resolve(store, [folder.parent])   # 触发 relocate 解析
    assert Path(out[0].path) == moved.resolve()       # 返回值里路径已找回(in-memory)
    assert out[0].status == "active"
    assert store.read_bytes() == before               # 但磁盘一字节未变(纯查询)


def test_save_is_atomic_no_temp_residue(tmp_path):
    store = tmp_path / "folders.json"
    f = registry.Folder(path="/x", uuid="u1", added_at="2026-06-03T00:00:00")
    registry.save(store, [f])
    # 内容完整可重载
    assert registry.load(store)[0].uuid == "u1"
    # 目录里只有目标文件，没有遗留的 .tmp 中间产物
    assert [p.name for p in tmp_path.iterdir()] == ["folders.json"]


def test_save_replaces_not_appends(tmp_path):
    store = tmp_path / "folders.json"
    a = registry.Folder(path="/a", uuid="ua", added_at="2026-06-03T00:00:00")
    b = registry.Folder(path="/b", uuid="ub", added_at="2026-06-03T00:00:01")
    registry.save(store, [a])
    registry.save(store, [b])           # 第二次覆盖
    loaded = registry.load(store)
    assert len(loaded) == 1 and loaded[0].uuid == "ub"

def test_archived_roundtrip(folder, tmp_path):
    store = tmp_path / "folders.json"
    _init(folder)
    u = registry.add(store, folder).uuid
    assert registry.load(store)[0].archived is False     # 默认未归档
    registry.set_archived(store, u, True)
    assert registry.load(store)[0].archived is True
    registry.set_archived(store, u, False)
    assert registry.load(store)[0].archived is False


def test_load_old_json_without_archived_defaults_false(tmp_path):
    # 向后兼容:旧 folders.json 没 archived 字段 → 默认 False,不崩
    store = tmp_path / "folders.json"
    store.write_text('[{"path":"/x","uuid":"u1","added_at":"2026-01-01T00:00:00","status":"active"}]')
    assert registry.load(store)[0].archived is False
