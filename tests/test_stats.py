from docx import Document

from dtm.engine.repo import GitRepo
from dtm.engine import backup, stats, listing, meta


def _commit(folder, text):
    repo = GitRepo(folder)
    if not repo.is_repo():
        repo.init()
        (folder / ".gitignore").write_text(backup.gitignore_text())
    doc = Document()
    doc.add_paragraph(text)
    doc.save(folder / "正文.docx")
    return repo, backup.do_backup(repo, folder).commit_id


def test_stats_reports_size_and_count(folder):
    repo, _ = _commit(folder, "A")
    _commit(folder, "B")
    s = stats.repo_stats(repo)
    assert s.version_count == 2
    assert s.git_bytes > 0


def test_listing_echoes_note_and_relative_time(folder):
    repo, cid = _commit(folder, "A")
    meta.set_note(repo, cid, "导师说结论太弱")
    rows = listing.build_version_list(repo)
    assert any("导师说结论太弱" in r.note for r in rows)
    assert all(r.when for r in rows)  # 相对时间非空
