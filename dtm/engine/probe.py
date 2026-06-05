"""性能探针——已退役（Windows 卡顿诊断完成:5个daemon/家目录扫描/git调用次数全已定位并修）。

保留为零开销空壳:全部 no-op、不再写 probe.log、不跑 tasklist/benchmark。
各调用点(repo/meta/bridge/daemon/gui)遂变成免费空操作,无需逐个拆除、零风险。
若日后再要诊断,把下面任一函数恢复成写文件即可。"""
from __future__ import annotations

from contextlib import contextmanager


def record_git(args, dt: float) -> None:
    pass


def proc(label: str) -> None:
    pass


def census() -> None:
    pass


def benchmark() -> None:
    pass


@contextmanager
def profile(label: str):
    yield
