"""提交信息：机器可解析 + 人类可读。绝不暴露 git 术语（INV-6）。"""
from __future__ import annotations

import re
import datetime

_PREFIX = "[dtm]"
_RE = re.compile(r"^\[dtm\] (?P<iso>\S+) \| (?P<summary>.*) \| (?P<source>\w+)$")


def _kb(delta_bytes: int) -> str:
    kb = round(delta_bytes / 1024)
    sign = "+" if kb >= 0 else ""
    return f"{sign}{kb}KB"


def build_message(iso_time, files, delta_bytes: int, source: str) -> str:
    if isinstance(files, str):
        summary = f"{files}({_kb(delta_bytes)})"
    elif len(files) == 1:
        summary = f"{files[0]}({_kb(delta_bytes)})"
    else:
        summary = f"{len(files)} 个文件({_kb(delta_bytes)})"
    return f"{_PREFIX} {iso_time} | {summary} | {source}"


def parse_message(message: str) -> dict:
    m = _RE.match(message.strip())
    if not m:
        return {"iso": "", "summary": message, "source": "auto"}
    return m.groupdict()


def humanize_time(unix_ts: int, now: datetime.datetime | None = None) -> str:
    now = now or datetime.datetime.now().astimezone()
    then = datetime.datetime.fromtimestamp(unix_ts).astimezone()
    delta = now - then
    secs = delta.total_seconds()
    if secs < 60:
        return "刚刚"
    if secs < 3600:
        return f"{int(secs // 60)} 分钟前"
    if then.date() == now.date():
        return f"今天 {then:%H:%M}"
    if (now.date() - then.date()).days == 1:
        return f"昨天 {then:%H:%M}"
    return f"{then:%m-%d %H:%M}"
