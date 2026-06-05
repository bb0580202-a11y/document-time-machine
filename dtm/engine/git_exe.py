"""解析该用哪个 git 可执行程序。

分层纪律：app 层决定何时设环境变量 DTM_GIT(指向内置 git 的绝对路径)，
engine 永远只是「DTM_GIT 有则用、无则回落系统 PATH 上的 git」——
engine 不知道打包/_MEIPASS/内置这些概念。

故无论 Spike 0 成功(app 恒设 DTM_GIT=内置)还是走逃生口方案2
(app 仅在系统无 git 时才设)，本模块一字不改。
"""
from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys

ENV_VAR = "DTM_GIT"

# app 层可注入的「跑 git 子进程前后清理进程环境」上下文工厂(分层:engine 不知打包/_MEIPASS)。
# 由头=PyInstaller(Windows) bootloader 调 SetDllDirectoryW(_MEIPASS),此设置被子进程继承,
# 内置 git.exe 遂从 _internal 加载到 ABI 不兼容的同名 DLL → 0xc0000142 STATUS_DLL_INIT_FAILED。
# app 层(runtime)在 frozen+win32 注入「临时撤销 SetDllDirectory + 剥 PATH」的上下文;
# 默认 None = no-op(开发态 / Mac 便携 git 依赖系统库、无此污染)。
_subprocess_prep_factory = None


def set_subprocess_prep(factory) -> None:
    """app 层注入清理上下文工厂(无参→返回 context manager);传 None 可复位(测试用)。"""
    global _subprocess_prep_factory
    _subprocess_prep_factory = factory


@contextlib.contextmanager
def subprocess_prep():
    """包住每一次 git 子进程调用:有注入则借它清理/恢复环境,无则 no-op。"""
    if _subprocess_prep_factory is None:
        yield
    else:
        with _subprocess_prep_factory():
            yield


def subprocess_kwargs() -> dict:
    """调 git 的平台相关 subprocess kwargs:Windows 隐藏 console 黑窗(GUI app 别闪屏)。"""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def git_path() -> str:
    """调用 git 时该用的可执行程序：DTM_GIT 优先，否则系统 PATH 上的 git。"""
    env = os.environ.get(ENV_VAR)
    if env:
        return env
    return shutil.which("git") or "git"


def git_available() -> bool:
    """git 是否可用：设了 DTM_GIT 则检查该路径可执行；否则看系统 PATH。"""
    env = os.environ.get(ENV_VAR)
    if env:
        return os.path.isfile(env) and os.access(env, os.X_OK)
    return shutil.which("git") is not None
