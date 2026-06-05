import subprocess

from dtm.engine.repo import GitRepo, git_available


def test_git_available():
    assert git_available() is True


def test_init_commit_log_roundtrip(folder, make_docx_factory):
    repo = GitRepo(folder)
    repo.init()
    make_docx_factory(folder / "正文.docx", "A")
    repo.add_all()
    cid = repo.commit("[dtm] test | 正文.docx(+1KB) | auto")
    assert len(cid) == 40
    entries = repo.log()
    assert len(entries) == 1
    assert entries[0].commit_id == cid
    assert "正文.docx" in entries[0].message


def test_no_network_remote_configured(folder):
    repo = GitRepo(folder)
    repo.init()
    remotes = subprocess.run(
        ["git", "-C", str(folder), "remote"], capture_output=True, text=True
    ).stdout.strip()
    assert remotes == ""  # 绝不配置任何 remote (INV-4)


def test_show_file_at_commit(folder, make_docx_factory):
    repo = GitRepo(folder)
    repo.init()
    make_docx_factory(folder / "正文.docx", "A")
    repo.add_all()
    cid = repo.commit("v1")
    raw = repo.show_file(cid, "正文.docx")
    assert raw[:2] == b"PK"  # docx 是 zip


def test_init_sets_cross_platform_config(folder):
    # 跨盘搬家/跨平台稳:filemode/autocrlf 关掉,避免 exFAT 权限位+行尾噪音
    repo = GitRepo(folder)
    repo.init()
    g = lambda k: subprocess.run(["git", "-C", str(folder), "config", k],
                                 capture_output=True, text=True).stdout.strip()
    assert g("core.filemode") == "false"
    assert g("core.autocrlf") == "false"
