import subprocess
import sys


def _run(args, cwd):
    return subprocess.run([sys.executable, "-m", "dtm.cli", *args],
                          cwd=str(cwd), capture_output=True, text=True)


def test_init_then_list(folder, make_docx_factory):
    make_docx_factory(folder / "正文.docx", "A")
    r = _run(["init", str(folder)], folder)
    assert r.returncode == 0, r.stderr
    assert "纳入备份" in r.stdout            # 首次清单透明性

    from dtm.engine.repo import GitRepo
    from dtm.engine import backup
    make_docx_factory(folder / "正文.docx", "B")
    backup.do_backup(GitRepo(folder), folder)

    r = _run(["list", str(folder)], folder)
    assert r.returncode == 0, r.stderr
    assert "正文.docx" in r.stdout


def test_no_git_terms_in_output(folder, make_docx_factory):
    make_docx_factory(folder / "正文.docx", "A")
    out = _run(["init", str(folder)], folder).stdout.lower()
    for term in ("commit", "branch", "head", "reflog", "git "):
        assert term not in out
