import subprocess

from dtm.engine.repo import GitRepo
from dtm.engine.health import check_repo, deep_check


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


# ---- 深度体检(全量 fsck,逮历史深处坏块) ----

def test_deep_check_healthy(folder):
    repo = _committed_repo(folder)
    ok, reason = deep_check(repo)
    assert ok is True and reason == ""


def test_deep_check_not_a_repo_is_ok(tmp_path):
    ok, _ = deep_check(GitRepo(tmp_path))
    assert ok is True


def test_deep_check_detects_rotted_blob(folder):
    # 真造硬盘坏块:把某个 blob 的 loose 对象内容改坏 → fsck 重算 SHA-1 应判坏。
    # 关键:这是 check_repo(只看 HEAD)逮不到的"历史深处坏块"——deep_check 才逮得到。
    repo = _committed_repo(folder)
    blob = subprocess.run(
        ["git", "-C", str(folder), "rev-parse", "HEAD:a.txt"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    obj = folder / ".git" / "objects" / blob[:2] / blob[2:]
    obj.chmod(0o644)                       # loose 对象默认只读
    obj.write_bytes(b"rotted garbage, not a valid zlib git object")
    ok, reason = deep_check(repo)
    assert ok is False
    assert "损坏" in reason                 # 人话告警 + 催"赶紧另拷一份"
