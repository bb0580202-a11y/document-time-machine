"""pywebview 窗口入口。spawn 子进程里运行:挂 Bridge 为 js_api,载入本地前端。"""
from __future__ import annotations
import sys
from pathlib import Path
import webview
from .bridge import Bridge

# 冻结后前端在 sys._MEIPASS/web;开发态回落包目录旁的 web/
_WEB = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "web" / "index.html"


def run_window():
    if sys.platform == "win32":
        # 声明 DPI 感知:否则 Windows 把整个 app 当低分辨率位图放大→又大又糊。
        # 声明后 WebView2 按系统缩放原生渲染前端(清晰、尺寸正常)。必须在建窗前调。
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PER_MONITOR_AWARE
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    from ..engine import probe
    probe.proc("gui.run_window(=GUI子进程,不该有托盘)")   # 若它之后又出现 daemon.run,就是 spawn 重跑了主程序
    from .runtime import install_git_subprocess_prep
    install_git_subprocess_prep()   # GUI 进程也调 git(Bridge 写操作),自注册(spawn 不继承模块级 hook)
    api = Bridge()
    w, h = 1000, 680                      # 默认收小一点
    if sys.platform == "win32":
        try:
            import ctypes
            u = ctypes.windll.user32
            sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)   # 屏幕物理像素(已 DPI 感知)
            w = max(720, min(w, int(sw * 0.70)))   # 不超屏幕 70%/82%,也不小于最小可用
            h = max(520, min(h, int(sh * 0.82)))
        except Exception:
            pass
    with probe.profile("gui.create_window"):
        webview.create_window("文档时光机", url=str(_WEB), js_api=api,
                              width=w, height=h, min_size=(720, 520))
    probe.census()                       # GUI 进程起来后数一次(看是否多出 daemon)
    with probe.profile("gui.webview.start"):
        webview.start()
