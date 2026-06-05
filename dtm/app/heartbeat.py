"""守护"我还在"心跳 + 裸奔回看(盲区5)。

死掉的进程喊不出话——所以"守护停过"不靠它自己报,靠**下次活着启动的守护**回看上次心跳算出空窗,
再由 GUI 开窗时告诉用户。重启本身交给 OS(Mac launchd / Win 计划任务),这里只管让用户知情。"""
from __future__ import annotations
import json
import os
import time
from pathlib import Path

BEAT_INTERVAL = 60.0       # 秒:多久留一次"我还在"
GAP_THRESHOLD = 600.0      # 秒:空窗超过这个才提醒(短于此=重启/重登录,别吵;约 10 分钟)


def write_beat(path: Path, clean: bool = False) -> None:
    """原子写心跳。clean=True 表示"我是故意走的"(用户主动退出),下次不当裸奔。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"ts": time.time(), "clean": clean})
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    tmp.write_text(payload)
    os.replace(tmp, path)


def read_beat(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def detect_gap(prev: dict | None, now: float, threshold: float = GAP_THRESHOLD) -> float | None:
    """纯判断:这次启动前是否有一段"没人守"的空窗值得提醒。返回空窗秒数或 None。
    - prev None(首次运行)→ None;
    - prev.clean(上次干净退出)→ None(正常关机不是裸奔);
    - 没打招呼就断、且空窗 > threshold → 返回空窗秒数;否则 None(太短不吵)。"""
    if not prev:
        return None
    if prev.get("clean"):
        return None
    gap = now - prev.get("ts", now)
    return gap if gap > threshold else None
