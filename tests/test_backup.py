from dtm.engine.repo import GitRepo
from dtm.engine import identity, backup
from tests.conftest import git_log_files


def _init(folder):
    repo = GitRepo(folder)
    repo.init()
    identity.write_identity(folder)
    (folder / ".gitignore").write_text(backup.gitignore_text())
    return repo


def test_first_backup_returns_manifest(folder, make_docx_factory):
    repo = _init(folder)
    make_docx_factory(folder / "正文.docx", "A")
    (folder / "~$正文.docx").write_bytes(b"lock")
    (folder / "temp.tmp").write_text("junk")
    result = backup.do_backup(repo, folder, source="auto")
    assert result.committed is True
    assert "正文.docx" in result.manifest
    assert "~$正文.docx" not in result.manifest
    assert "temp.tmp" not in result.manifest


def test_ignored_files_never_enter_history(folder, make_docx_factory):
    repo = _init(folder)
    make_docx_factory(folder / "正文.docx", "A")
    (folder / "~$正文.docx").write_bytes(b"lock")
    backup.do_backup(repo, folder, source="auto")
    files = git_log_files(folder)
    assert "正文.docx" in files
    assert "~$正文.docx" not in files


def test_large_file_backed_up_with_warning(folder):
    repo = _init(folder)
    big = folder / "大图.bin"
    big.write_bytes(b"\0" * (51 * 1024 * 1024))
    result = backup.do_backup(repo, folder, source="auto")
    assert any("大图.bin" in w for w in result.warnings)
    assert "大图.bin" in git_log_files(folder)  # 仍然备份 (INV-2)


def test_no_change_no_commit(folder, make_docx_factory):
    repo = _init(folder)
    make_docx_factory(folder / "正文.docx", "A")
    backup.do_backup(repo, folder, source="auto")
    second = backup.do_backup(repo, folder, source="auto")
    assert second.committed is False
