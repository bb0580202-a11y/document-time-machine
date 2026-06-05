from dtm.engine.repo import GitRepo
from dtm.engine import backup, meta


def _one_commit(folder, make_docx_factory):
    repo = GitRepo(folder)
    repo.init()
    (folder / ".gitignore").write_text(backup.gitignore_text())
    make_docx_factory(folder / "正文.docx", "A")
    return repo, backup.do_backup(repo, folder).commit_id


def test_note_set_get_clear_no_new_version(folder, make_docx_factory):
    repo, cid = _one_commit(folder, make_docx_factory)
    before = len(repo.log())
    meta.set_note(repo, cid, "导师说结论太弱")
    assert meta.get_note(repo, cid) == "导师说结论太弱"
    assert len(repo.log()) == before          # 备注不产生新快照
    meta.set_note(repo, cid, "")               # 清空
    assert meta.get_note(repo, cid) == ""
    assert len(repo.log()) == before


def test_tag_milestone(folder, make_docx_factory):
    repo, cid = _one_commit(folder, make_docx_factory)
    meta.set_tag(repo, cid, "投稿前")
    assert "投稿前" in meta.tags_for(repo, cid)


def test_remove_tag_keeps_version(folder, make_docx_factory):
    repo, cid = _one_commit(folder, make_docx_factory)
    before = len(repo.log())
    meta.set_tag(repo, cid, "投稿前")
    meta.remove_tag(repo, "投稿前")              # 删标签
    assert meta.tags_for(repo, cid) == []
    assert len(repo.log()) == before             # 版本本身不受影响(INV-1)
    meta.remove_tag(repo, "投稿前")              # 幂等:再删不报错
