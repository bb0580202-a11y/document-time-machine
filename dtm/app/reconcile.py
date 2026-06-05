"""守护编排的纯决策:对比「期望被监听的文件夹」与「当前在监听的」,算出该起/停/重起谁。
纯函数、零副作用、可单测——决策与真实起停 watcher 的副作用(daemon 里、动线程)分离,
复用 treemap 那套「逻辑纯可测、效果薄可验」。放 app 层:这是守护编排,不碰 git/repo。"""
from __future__ import annotations


def plan_reconcile(
    desired: dict[str, str], running: dict[str, str]
) -> tuple[set[str], set[str], set[str]]:
    """desired/running 均为 {uuid: path}。返回 (to_start, to_stop, to_restart) 三个 uuid 集合。
    - to_start:   desired 有、running 无 → 起新 watcher。
    - to_stop:    running 有、desired 无 → 停掉。
    - to_restart: uuid 同但 path 变了(relocate) → 停旧按新 path 重起。
    幂等:同状态重复调 → 三集合全空。"""
    to_start = {u for u in desired if u not in running}
    to_stop = {u for u in running if u not in desired}
    to_restart = {u for u in desired if u in running and desired[u] != running[u]}
    return to_start, to_stop, to_restart
