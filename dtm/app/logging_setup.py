"""把日志写进 配置目录/dtm.log。

为什么落文件不靠 stdout:打包成 .app 后根本没有终端,stdout 的日志直接蒸发,
"兜底排查"就成了空头支票(守护自检结果、备份失败原因都得捞得到)。给排查用,不是给小白。"""
from __future__ import annotations
import logging
from pathlib import Path

from ..engine import registry


def setup_file_logging() -> Path:
    """给 root logger 挂一个写 配置目录/dtm.log 的 FileHandler(同进程重复调不重复挂)。"""
    log_path = registry.default_store().parent / "dtm.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    already = any(
        isinstance(h, logging.FileHandler)
        and getattr(h, "baseFilename", "") == str(log_path)
        for h in root.handlers
    )
    if not already:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root.addHandler(handler)
    return log_path
