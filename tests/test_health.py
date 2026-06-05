from dtm.engine.repo import GitRepo
from dtm.engine.health import check_repo


def _committed_repo(folder):
    repo = GitRepo(folder)
    repo.init()
    (folder / "a.txt").write_text("x")
    repo.add_all()
    repo.commit("m")
    return repo


def test_check_repo_healthy(folder):
    repo = _committed_repo(folder)
    ok, reason = check_repo(repo)
    assert ok is True and reason == ""


def test_check_repo_not_a_repo_is_ok(tmp_path):
    # 没 .git 不归"损坏"管(是夹没了/没初始化,另一类问题)
    ok, reason = check_repo(GitRepo(tmp_path))
    assert ok is True


def test_check_repo_detects_corrupt_head_commit(folder):
    # 真造坏仓:删掉 HEAD 那笔 commit 对象(模拟断电打断写入)→ 读不出 → 判坏、不崩
    repo = _committed_repo(folder)
    cid = repo.head()
    obj = folder / ".git" / "objects" / cid[:2] / cid[2:]
    obj.unlink()
    ok, reason = check_repo(repo)
    assert ok is False
    assert "损坏" in reason            # 人话告警(hedge 用词)


def test_check_repo_detects_broken_ref(folder):
    # 真造坏仓:把 HEAD 指向的分支 ref 写成不存在的对象
    repo = _committed_repo(folder)
    head = (folder / ".git" / "HEAD").read_text().strip()
    ref = head.split(" ", 1)[1] if head.startswith("ref:") else "refs/heads/master"
    (folder / ".git" / ref).write_text("0" * 40 + "\n")
    ok, reason = check_repo(repo)
    assert ok is False
