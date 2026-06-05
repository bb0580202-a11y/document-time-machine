"""开机自启抽象。启动命令/路径当参数传入，不硬编码 —— Phase 3 打包后只换参数。
macOS：写 ~/Library/LaunchAgents/<label>.plist，RunAtLoad=true 登录即起、
KeepAlive={SuccessfulExit:False}（干净退出不被拉起，只有崩溃才重启）。Windows：留 stub。

**纯文件操作、app 绝不碰 launchctl**：install=写 plist、uninstall=删 plist，
加载/卸载交给 OS 的登录/注销（RunAtLoad 在登录时 load、注销时 unload）。
故意不在 uninstall 里 `bootout`——否则重登录后 launchd 管着守护时,关开关会把正跑的守护
一并干掉,违背「关开关只停自启、不杀当前守护」(设计 §4D / bb 定)。plist_dir 可注入,测试只往 tmp 写。"""
from __future__ import annotations
import plistlib
import sys
from pathlib import Path
from .errors import DtmError

_MAC_LABEL = "com.doc-time-machine.daemon"


class AutoStart:
    def install(self, command: list[str]) -> None:
        raise NotImplementedError

    def uninstall(self) -> None:
        raise NotImplementedError

    def is_enabled(self) -> bool:
        raise NotImplementedError


def build_launchd_plist(label: str, command: list[str]) -> dict:
    return {
        "Label": label,
        "ProgramArguments": list(command),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
    }


class MacAutoStart(AutoStart):
    def __init__(self, label: str = _MAC_LABEL, plist_dir: Path | None = None):
        self.label = label
        self.plist_dir = Path(plist_dir) if plist_dir else (
            Path.home() / "Library" / "LaunchAgents")

    @property
    def plist_path(self) -> Path:
        return self.plist_dir / f"{self.label}.plist"

    def install(self, command: list[str]) -> None:
        # 只装不 load-now:只写 plist,下次开机由 launchd RunAtLoad 加载。
        # 不 bootstrap → 根治"开开关时已有手动守护抢 flock"的拉锯(设计 §4D)。
        self.plist_dir.mkdir(parents=True, exist_ok=True)
        with open(self.plist_path, "wb") as fh:
            plistlib.dump(build_launchd_plist(self.label, command), fh)

    def uninstall(self) -> None:
        # 只删 plist=下次开机不再自启;不 bootout=当前这次登录正跑的守护继续活到下次注销
        # (=「关开关只停自启、不杀当前守护」)。已 load 的作业由 OS 注销时自然 unload。
        try:
            self.plist_path.unlink()
        except FileNotFoundError:
            pass

    def is_enabled(self) -> bool:
        return self.plist_path.exists()


def _join_cmd(command: list[str]) -> str:
    """把命令拼成 Run 值字符串(含空格的段加引号)。"""
    return " ".join(f'"{c}"' if " " in c else c for c in command)


class _WinregBackend:
    """真注册表后端。winreg 仅 Windows 有 → lazy import(Mac 上 get_autostart 返回 Mac 实现,永不走到)。"""
    def __init__(self, run_key: str):
        import winreg
        self._wr = winreg
        self._run_key = run_key

    def _open(self, access):
        return self._wr.OpenKey(self._wr.HKEY_CURRENT_USER, self._run_key, 0, access)

    def set(self, name: str, value: str) -> None:
        with self._open(self._wr.KEY_SET_VALUE) as k:
            self._wr.SetValueEx(k, name, 0, self._wr.REG_SZ, value)

    def get(self, name: str):
        try:
            with self._open(self._wr.KEY_READ) as k:
                v, _ = self._wr.QueryValueEx(k, name)
                return v
        except FileNotFoundError:
            return None

    def delete(self, name: str) -> None:
        try:
            with self._open(self._wr.KEY_SET_VALUE) as k:
                self._wr.DeleteValue(k, name)
        except FileNotFoundError:
            pass


class WindowsAutoStart(AutoStart):
    """开机自启 Windows 实现:写 HKCU\\…\\Run 值=登录时启动。
    ⚠️ 仅"登录启动",**崩后不重启**(Run 键管不了)——崩后恢复要 Task Scheduler/服务,留后续(robustness backlog)。
    backend 可注入:测试用假 backend 验逻辑、不碰真注册表(winreg lazy,Mac 单测得了);真机"登录是否真自启"待 Windows CP。"""
    _RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def __init__(self, label: str = _MAC_LABEL, backend=None):
        self.label = label
        self._backend = backend

    def _be(self):
        if self._backend is None:
            self._backend = _WinregBackend(self._RUN_KEY)   # 用时才建(lazy winreg)
        return self._backend

    def install(self, command: list[str]) -> None:
        self._be().set(self.label, _join_cmd(command))

    def uninstall(self) -> None:
        self._be().delete(self.label)

    def is_enabled(self) -> bool:
        return self._be().get(self.label) is not None


def get_autostart(label: str = _MAC_LABEL, plist_dir: Path | None = None) -> AutoStart:
    if sys.platform == "darwin":
        return MacAutoStart(label, plist_dir)
    if sys.platform == "win32":
        return WindowsAutoStart()
    raise DtmError("当前系统暂不支持开机自启。")
