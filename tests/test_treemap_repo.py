from pathlib import Path
from docx import Document
from dtm.engine.repo import GitRepo
from dtm.engine import backup, treemap


def _commit(folder, text):
    repo = GitRepo(folder)
    if not repo.is_repo():
        repo.init()
        (folder / ".gitignore").write_text(backup.gitignore_text())
    d = Document(); d.add_paragraph(text); d.save(folder / "正文.docx")
    return repo, backup.do_backup(repo, folder).commit_id


def test_branches_lists_tips(folder):
    repo, base = _commit(folder, "A")
    repo.create_branch("路线-2", base)
    tips = repo.branches()
    assert base in tips.values()
    assert "路线-2" in tips


def test_from_repo_builds_treemap_with_two_lanes(folder):
    repo, base = _commit(folder, "A")
    main_name = repo.current_branch()
    repo.create_branch("路线-2", base)
    repo.checkout("路线-2")
    _commit(folder, "岔路改动")
    tm = treemap.from_repo(repo, main_branch=main_name)
    lanes = sorted(l.index for l in tm.lanes)
    assert lanes == [0, 1]                      # 主线 + 一条分支
    assert any(n.is_branch_point for n in tm.nodes)
