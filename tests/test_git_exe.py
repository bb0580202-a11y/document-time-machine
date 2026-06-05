import contextlib
import os
import shutil
import sys
import pytest
from dtm.engine import git_exe
from dtm.engine.git_exe import (
    git_path, git_available, ENV_VAR, subprocess_prep, subprocess_kwargs,
    set_subprocess_prep,
)
from dtm.engine.repo import GitRepo
from dtm.engine.errors import GitUnavailableError


def test_git_path_prefers_dtm_git_env(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "/opt/dtm/git")
    assert git_path() == "/opt/dtm/git"


def test_git_path_falls_back_to_system_when_env_unset(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert git_path() == (shutil.which("git") or "git")


def test_git_available_true_when_env_points_to_executable(monkeypatch, tmp_path):
    fake = tmp_path / "git"
    fake.write_text("#!/bin/sh\n")
    os.chmod(fake, 0o755)
    monkeypatch.setenv(ENV_VAR, str(fake))
    assert git_available() is True


def test_git_available_false_when_env_points_to_missing(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "/nonexistent/git")
    assert git_available() is False


def test_git_available_falls_back_to_system(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert git_available() is True  # 开发/测试机有系统 git


def test_gitrepo_honors_dtm_git_env(folder, make_docx_factory, monkeypatch):
    # 把 DTM_GIT 指向真实系统 git，跑通全套 → 证明 repo 经 git_path() 路由
    monkeypatch.setenv(ENV_VAR, shutil.which("git"))
    repo = GitRepo(folder)
    repo.init()
    make_docx_factory(folder / "正文.docx", "A")
    repo.add_all()
    cid = repo.commit("v1")
    assert len(cid) == 40
    assert repo.show_file(cid, "正文.docx")[:2] == b"PK"


def test_gitrepo_raises_when_dtm_git_bogus(folder, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "/nonexistent/git")
    repo = GitRepo(folder)
    with pytest.raises(GitUnavailableError):
        repo.init()


# ---------- subprocess prep / kwargs(Windows DLL 污染 + 闪窗的接线) ----------

def test_subprocess_prep_default_is_noop():
    # 未注入(默认)→ 进出不报错、纯透传(Mac/开发态)
    with subprocess_prep():
        pass


def test_subprocess_prep_uses_injected_factory(monkeypatch):
    # app 层注入的清理上下文会被每次 git 调用真正进出(分层 plumbing 接线证明)
    events = []

    @contextlib.contextmanager
    def fake_prep():
        events.append("enter")
        try:
            yield
        finally:
            events.append("exit")

    monkeypatch.setattr(git_exe, "_subprocess_prep_factory", fake_prep)
    with subprocess_prep():
        events.append("inside")
    assert events == ["enter", "inside", "exit"]


def test_set_subprocess_prep_registers_and_resets():
    sentinel = object()
    set_subprocess_prep(lambda: sentinel)
    assert git_exe._subprocess_prep_factory() is sentinel
    set_subprocess_prep(None)               # 复位
    with subprocess_prep():                  # 复位后回到 no-op
        pass


def test_subprocess_kwargs_clean_on_non_windows():
    # 非 Windows(测试机=Mac/Linux):不加 creationflags,纯净 kwargs
    if sys.platform != "win32":
        assert subprocess_kwargs() == {}
    else:                                    # Windows 上才隐藏黑窗(真机/Win CI)
        import subprocess
        assert subprocess_kwargs() == {"creationflags": subprocess.CREATE_NO_WINDOW}
