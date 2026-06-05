from dtm.engine.repo import GitRepo
from dtm.engine import identity


def test_write_and_read_identity(folder):
    GitRepo(folder).init()
    ident = identity.write_identity(folder)
    assert ident["created_by"] == "doc-time-machine"
    assert len(ident["uuid"]) >= 16
    again = identity.read_identity(folder)
    assert again["uuid"] == ident["uuid"]


def test_find_by_uuid(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    GitRepo(a).init()
    ident = identity.write_identity(a)
    moved = tmp_path / "moved"
    a.rename(moved)
    found = identity.find_repo_by_uuid(ident["uuid"], [tmp_path])
    assert found == moved
