"""app 层运行时设施：解析内置 git 位置并设入 DTM_GIT。

仅 app 层知道打包/_MEIPASS;engine 只读 DTM_GIT env(见 engine/git_exe.py)。
默认策略(方案1,Spike0 已锁):恒设 DTM_GIT=内置 git。
(逃生口方案2若启用,改为:系统有 git 时不设、没有才设——仅此函数内分支,engine 不变。)
"""
from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

from dtm.engine import git_exe
from dtm.engine.git_exe import ENV_VAR


def _bundle_root() -> Path:
    # 冻结后资源根 = sys._MEIPASS;未冻结(开发)回落包目录
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def bundled_git_path() -> Path | None:
    """内置 git 的绝对路径;不存在(开发态/未打包)返回 None。
    布局随平台:Mac(Spike0)= <root>/git/bin/git;Windows(MinGit)= <root>/git/cmd/git.exe。
    (engine/git_exe.py 只读 DTM_GIT env、不关心布局;布局差异只此一处。)"""
    root = _bundle_root()
    p = root / "git" / "cmd" / "git.exe" if sys.platform == "win32" else root / "git" / "bin" / "git"
    return p if p.exists() else None


def daemon_launch_command() -> list[str]:
    """自启拉起守护的命令:冻结=.app 入口本就是守护;开发=python -m。
    根治 cli.py 硬编码 sys.executable -m(冻结后指错)的老坑。"""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "dtm.cli", "daemon"]


def _is_under(path_value: str, root: str) -> bool:
    """path_value 是否锚定在 root 目录下(用于从 PATH 剥 _MEIPASS 子路径)。"""
    try:
        return os.path.commonpath([os.path.abspath(path_value), root]) == root
    except ValueError:     # 不同盘符(Windows C: vs D:)→ commonpath 抛,显然不在其下
        return False


def install_git_subprocess_prep() -> None:
    """frozen+win32:注入「跑 git 前临时撤销 PyInstaller 的 DLL 搜索路径污染」上下文。

    PyInstaller bootloader 调 SetDllDirectoryW(_MEIPASS),此进程级设置被子进程继承;
    内置 git.exe 遂从 _internal 加载到 ABI 不兼容的同名 DLL → 0xc0000142。
    对策(官方):调外部程序前 SetDllDirectoryW(None) + 从 PATH 剥 _MEIPASS,调完恢复
    (恢复是必须的:GUI 子进程自身仍需 _MEIPASS 的 WebView2/CLR DLL)。
    守护与 GUI 两进程入口各调一次(spawn 子进程重 import、模块级 hook 不继承)。
    Mac/开发态不注入(便携 git 依赖系统库、无此污染),保持 engine 默认 no-op。"""
    if not (getattr(sys, "frozen", False) and sys.platform == "win32"):
        return
    import ctypes
    meipass = str(_bundle_root())
    kernel32 = ctypes.windll.kernel32

    @contextlib.contextmanager
    def _prep():
        old_path = os.environ.get("PATH", "")
        kernel32.SetDllDirectoryW(None)        # 撤销 PyInstaller 注入的 DLL 目录
        sep = os.pathsep
        os.environ["PATH"] = sep.join(
            p for p in old_path.split(sep) if p and not _is_under(p, meipass)
        )
        try:
            yield
        finally:
            kernel32.SetDllDirectoryW(meipass)  # 恢复:本进程后续/GUI 仍需 _MEIPASS 的 DLL
            os.environ["PATH"] = old_path

    git_exe.set_subprocess_prep(_prep)


def ensure_git_env() -> None:
    """在 spawn 任何子进程之前调用:把 DTM_GIT 设好,子进程经 os.environ 继承。"""
    g = bundled_git_path()
    if g is not None:
        # 防御:打包可能丢执行位(坑/bb 提醒),补回
        if not os.access(g, os.X_OK):
            try:
                os.chmod(g, 0o755)
            except OSError:
                pass
        os.environ[ENV_VAR] = str(g)
    # 内置不存在(开发态)则不设,engine 回落系统 git——不报错,方便本机开发
