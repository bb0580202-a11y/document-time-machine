import plistlib
import pytest
from dtm.engine.autostart import build_launchd_plist, MacAutoStart, WindowsAutoStart


def test_build_plist_keepalive_is_dict_not_true():
    p = build_launchd_plist("com.x.daemon", ["python", "-m", "dtm.cli", "daemon"])
    # 关键：KeepAlive 必须是 {SuccessfulExit: False}，否则托盘"退出"会被 launchd 拉起
    assert p["KeepAlive"] == {"SuccessfulExit": False}
    assert p["RunAtLoad"] is True
    assert p["ProgramArguments"] == ["python", "-m", "dtm.cli", "daemon"]
    assert p["Label"] == "com.x.daemon"


def test_install_writes_loadable_plist(tmp_path):
    # plist_dir 注入到 tmp → 不碰真实 ~/Library
    a = MacAutoStart(label="com.x.daemon", plist_dir=tmp_path)
    assert a.is_enabled() is False
    a.install(["python", "-m", "dtm.cli", "daemon"])
    assert a.is_enabled() is True
    with open(a.plist_path, "rb") as fh:
        data = plistlib.load(fh)
    assert data["KeepAlive"] == {"SuccessfulExit": False}


def test_install_uninstall_never_touch_launchctl(tmp_path, monkeypatch):
    # 纯文件操作:install/uninstall 绝不跑 launchctl(加载/卸载交给 OS 登录/注销)。
    # 关键:uninstall 不 bootout → 重登录后关开关不会把正跑的守护干掉(设计 §4D)。
    import subprocess
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))
    a = MacAutoStart(label="com.x.daemon", plist_dir=tmp_path)
    a.install(["python", "-m", "dtm.cli", "daemon"])
    a.uninstall()
    assert calls == []                  # 全程没碰 launchctl


def test_uninstall_removes_plist(tmp_path):
    a = MacAutoStart(label="com.x.daemon", plist_dir=tmp_path)
    a.install(["python", "-m", "dtm.cli", "daemon"])
    a.uninstall()
    assert a.is_enabled() is False


class _FakeReg:
    def __init__(self): self.d = {}
    def set(self, name, value): self.d[name] = value
    def get(self, name): return self.d.get(name)
    def delete(self, name): self.d.pop(name, None)


def test_windows_autostart_roundtrip():
    # 注入假注册表 backend → Mac 上单测 HKCU\Run 逻辑,不碰真 winreg
    be = _FakeReg()
    a = WindowsAutoStart(label="com.x.daemon", backend=be)
    assert a.is_enabled() is False
    a.install([r"C:\Program Files\dtm\doc-time-machine.exe"])
    assert a.is_enabled() is True
    assert be.d["com.x.daemon"] == r'"C:\Program Files\dtm\doc-time-machine.exe"'  # 含空格加引号
    a.uninstall()
    assert a.is_enabled() is False
