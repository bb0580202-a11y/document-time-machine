from dtm.app import runtime


def test_daemon_launch_command_dev(monkeypatch):
    monkeypatch.delattr("sys.frozen", raising=False)      # 开发态:无 sys.frozen
    cmd = runtime.daemon_launch_command()
    assert cmd[1:] == ["-m", "dtm.cli", "daemon"]          # python -m dtm.cli daemon


def test_daemon_launch_command_frozen(monkeypatch):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable",
                        "/Applications/X.app/Contents/MacOS/x", raising=False)
    # 冻结:.app 入口本就是守护,直接指可执行
    assert runtime.daemon_launch_command() == ["/Applications/X.app/Contents/MacOS/x"]


def test_bundled_git_path_windows(tmp_path, monkeypatch):
    # Windows MinGit 布局 cmd/git.exe(在 Mac 上也能单测这条分支逻辑)
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr(runtime, "_bundle_root", lambda: tmp_path)
    assert runtime.bundled_git_path() is None                    # 还没文件
    (tmp_path / "git" / "cmd").mkdir(parents=True)
    (tmp_path / "git" / "cmd" / "git.exe").write_text("")
    assert runtime.bundled_git_path() == tmp_path / "git" / "cmd" / "git.exe"


def test_bundled_git_path_unix(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(runtime, "_bundle_root", lambda: tmp_path)
    (tmp_path / "git" / "bin").mkdir(parents=True)
    (tmp_path / "git" / "bin" / "git").write_text("")
    assert runtime.bundled_git_path() == tmp_path / "git" / "bin" / "git"
