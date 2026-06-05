from docx import Document

from dtm.engine.repo import GitRepo
from dtm.engine import backup


def _save(folder, text):
    doc = Document()
    doc.add_paragraph(text)
    doc.save(folder / "正文.docx")


def test_branch_keeps_mainline_intact(folder):
    repo = GitRepo(folder)
    repo.init()
    (folder / ".gitignore").write_text(backup.gitignore_text())
    _save(folder, "主线")
    base = backup.do_backup(repo, folder).commit_id
    mainline = repo.current_branch()

    repo.create_branch("路线-2", base)
    repo.checkout("路线-2")
    _save(folder, "岔路改动")
    backup.do_backup(repo, folder)

    # 主线那条只有 base 一版，未受岔路影响
    main_log = repo.log(ref=mainline)
    assert len(main_log) == 1
    assert main_log[0].commit_id == base
    # 两条线在全量历史里都可见
    assert len(repo.log()) >= 2
