"""守护进程:托盘(主线程) + 按 registry 起 watcher 线程 + 托盘点击 spawn GUI 窗口。
动态监听:盯 config 目录,folders.json 一变(GUI 加/删)就 reconcile,不重启即生效。
成功安静(托盘低调)、失败响亮(托盘通知 + 人话原因)。退出干净。"""
from __future__ import annotations
import json
import logging
import multiprocessing as mp
import os
import sys
import threading
import time
from pathlib import Path
import pystray
from PIL import Image, ImageDraw
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from ..engine import registry, probe
from ..engine.repo import GitRepo
from ..engine.health import check_repo
from ..engine.watcher import watch
from .reconcile import plan_reconcile
from .logging_setup import setup_file_logging
from . import heartbeat
from . import gui
from . import single_instance

_CFG_DEBOUNCE = 1.0   # 秒:coalesce folders.json 的 os.replace 事件抖动


def should_open_window(cfg_dir: Path) -> bool:
    """有 open_window.req → 删之 + True;无 → False。第二实例 touch 这个 flag 叫醒已有守护开窗。"""
    try:
        (cfg_dir / "open_window.req").unlink()
        return True
    except FileNotFoundError:
        return False


def _icon_image():
    # 时钟图标(时光机):蓝圆角方底 + 白表盘 + 指针。别再像"圆点/国旗"。
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6, 6, 58, 58), radius=15, fill="#2563eb")
    d.ellipse((17, 17, 47, 47), outline="white", width=4)   # 表圈
    d.line((32, 32, 32, 21), fill="white", width=3)         # 时针
    d.line((32, 32, 41, 37), fill="white", width=3)         # 分针
    return img


class _CfgHandler(FileSystemEventHandler):
    """config 目录里任何事件 → 触发去抖 reconcile(事件只当脏标记)。"""
    def __init__(self, on_change):
        self._on_change = on_change

    def on_any_event(self, event):
        self._on_change()


class Daemon:
    def __init__(self):
        self.ctx = mp.get_context("spawn") if sys.platform == "darwin" else mp.get_context()
        self.store = registry.default_store()
        self.win = None
        self._inst_fd = None       # 单实例 flock 的 fd:main() 拿到后挂这里全程持有(关=释锁)
        self.running = {}          # uuid -> (path, observer, db, stop)
        self._lock = threading.Lock()   # 串 running 的增删:reconcile(定时器线程) vs quit(托盘线程)
        self._cfg_observer = None
        self._cfg_timer = None
        self._beat_path = self.store.parent / "heartbeat.json"
        self._downtime_path = self.store.parent / "downtime.json"
        self._beat_stop = threading.Event()

    # ---------- 心跳 / 裸奔回看(盲区5) ----------
    def detect_downtime_on_start(self):
        """启动时回看上次心跳:若是没打招呼就断、且空窗够久,记下这段空窗给 GUI 提醒。"""
        prev = heartbeat.read_beat(self._beat_path)
        gap = heartbeat.detect_gap(prev, time.time())
        if gap is not None:
            logging.warning("守护曾停止约 %d 秒,这期间未受保护(盲区5)", int(gap))
            tmp = self._downtime_path.parent / f".{self._downtime_path.name}.{os.getpid()}.tmp"
            tmp.write_text(json.dumps({"gap": gap, "ended_at": time.time()}))
            os.replace(tmp, self._downtime_path)

    def start_heartbeat(self):
        """立刻留一次"我还在",再每 BEAT_INTERVAL 秒续一次,直到 quit。"""
        self.store.parent.mkdir(parents=True, exist_ok=True)
        heartbeat.write_beat(self._beat_path, clean=False)

        def _loop():
            while not self._beat_stop.wait(heartbeat.BEAT_INTERVAL):
                heartbeat.write_beat(self._beat_path, clean=False)

        threading.Thread(target=_loop, daemon=True).start()

    # ---------- 动态对账 ----------
    def reconcile(self):
        """纯算 desired(resolve 不写盘) → plan_reconcile → 真起停 watcher。持锁改 running。"""
        # 不传 search_roots:resolve 对路径失效的库(pending)会递归扫整个家目录找 UUID,
        # 实测在 Windows 上卡 7 秒/次(× 多次对账=灾难)。守护只看路径还在的 active 库;
        # 搬走的库靠 GUI(list_folders 仍带 search_roots)用户开窗时找回,不在守护热路径上扫盘。
        folders = registry.resolve(self.store, [])
        desired = {f.uuid: f.path for f in folders if f.status == "active" and not f.archived}
        started = []
        with self._lock:
            running_paths = {u: t[0] for u, t in self.running.items()}
            to_start, to_stop, to_restart = plan_reconcile(desired, running_paths)
            for u in to_stop | to_restart:
                path, observer, db, stop = self.running.pop(u)
                stop.set(); db.cancel(); observer.stop(); observer.join()
            for u in to_start | to_restart:
                path = desired[u]
                repo = GitRepo(path)
                observer, db, stop = watch(repo, Path(path))
                self.running[u] = (path, observer, db, stop)
                started.append(path)
        if started:                 # 自检放后台线程:git subprocess(Windows 上每次~900ms),
            # 别阻塞 reconcile/启动(否则托盘要等 N×3 次 git 才出来)。坏库的红横幅晚一会儿没关系。
            threading.Thread(target=self._check_health_batch, args=(started,),
                             daemon=True).start()

    def _check_health_batch(self, paths):
        for path in paths:
            self._check_health(path)


    def _check_health(self, path):
        """启动/新加一个库时自检:坏了响亮记进 dtm.log(给排查);小白侧的红横幅由 GUI 出。"""
        ok, reason = check_repo(GitRepo(path))
        if not ok:
            logging.warning("仓库自检:%s 历史可能损坏——%s", path, reason)

    def _on_cfg_change(self):
        """去抖:最后一次 config 事件后静默 _CFG_DEBOUNCE 秒才结算一次。"""
        if self._cfg_timer:
            self._cfg_timer.cancel()
        self._cfg_timer = threading.Timer(_CFG_DEBOUNCE, self._on_cfg_settled)
        self._cfg_timer.daemon = True
        self._cfg_timer.start()

    def _on_cfg_settled(self):
        """去抖结算:先处理叫醒开窗(第二实例的 flag),再照常对账。两者都幂等。"""
        if should_open_window(self.store.parent):
            self.open_window()       # 复用现有单窗幂等(open_window 已 if not is_alive() 才 spawn)
        self.reconcile()             # 照常对账(多跑一次无害)

    def start_config_watch(self):
        # 首装兜底:config 目录可能还没被任何 save 创建(autostart 先跑)→ 先 mkdir,否则
        # Observer.schedule(不存在目录) 抛、守护启动即崩。
        cfg_dir = self.store.parent
        cfg_dir.mkdir(parents=True, exist_ok=True)
        self._cfg_observer = Observer()
        self._cfg_observer.schedule(_CfgHandler(self._on_cfg_change), str(cfg_dir), recursive=False)
        self._cfg_observer.start()

    def stop_config_watch(self):
        if self._cfg_timer:
            self._cfg_timer.cancel()
        if self._cfg_observer:
            self._cfg_observer.stop(); self._cfg_observer.join()
            self._cfg_observer = None

    # ---------- 托盘 / 窗口 ----------
    def open_window(self, icon=None, item=None):
        if self.win is None or not self.win.is_alive():
            self.win = self.ctx.Process(target=gui.run_window)
            self.win.start()

    def quit(self, icon, item):
        self._beat_stop.set()
        heartbeat.write_beat(self._beat_path, clean=True)   # 留"我是故意走的",下次不误报裸奔
        self.stop_config_watch()
        with self._lock:
            for u, (path, observer, db, stop) in list(self.running.items()):
                stop.set(); db.cancel(); observer.stop(); observer.join()
            self.running.clear()
        if self.win and self.win.is_alive():
            self.win.terminate()
        icon.stop()

    def _setup_tray(self, icon):
        # 事件循环起来后调:把托盘后台进程设为"附件/代理"(accessory),不占 Dock 位。
        # 仅 macOS;失败不致命(顶多守护多占一个 Dock 图标)。webview 子进程是另一进程、
        # 保持默认(regular),开窗时正常显示+聚焦+占一个 Dock 图标。
        icon.visible = True
        if sys.platform == "darwin":
            try:
                from AppKit import (NSApplication,
                                    NSApplicationActivationPolicyAccessory)
                NSApplication.sharedApplication().setActivationPolicy_(
                    NSApplicationActivationPolicyAccessory)
            except Exception:
                pass

    def run(self):
        with probe.profile("startup.detect_downtime"):
            self.detect_downtime_on_start()   # 先回看上次心跳(读旧记号)再续新心跳
        with probe.profile("startup.heartbeat"):
            self.start_heartbeat()
        with probe.profile("startup.reconcile"):
            self.reconcile()      # 启动:把当前 active 全起来(与动态新增走同一条 reconcile 路径)
        with probe.profile("startup.config_watch"):
            self.start_config_watch()
        menu = pystray.Menu(
            pystray.MenuItem("打开主界面", self.open_window, default=True),
            pystray.MenuItem("退出", self.quit),
        )
        pystray.Icon("doc-time-machine", _icon_image(), menu=menu).run(
            setup=self._setup_tray)  # 主线程


def main():
    mp.freeze_support()           # 必须最先:冻结后 spawn 子进程不重跑整个 app(多托盘 fork 炸弹)
    cfg_dir = registry.default_store().parent
    cfg_dir.mkdir(parents=True, exist_ok=True)   # freeze_support 后第一件事:日志和锁都依赖它
    setup_file_logging()          # 日志落 配置目录/dtm.log(打包后无终端,stdout 会蒸发)
    probe.proc("main-enter")      # 高密度探针:记进程身份(查"两托盘"是不是两 daemon)
    fd = single_instance.acquire(cfg_dir / "daemon.lock")
    probe.proc(f"acquire-result={'GOT-LOCK(主守护)' if fd is not None else 'NONE(应自退)'}")
    if fd is None:                # 已有守护在跑:叫醒它开窗,本进程自退
        (cfg_dir / "open_window.req").touch()
        logging.info("已有守护在跑,请求其开窗后本次退出")
        return                    # exit 0 → KeepAlive(SuccessfulExit:false)本次不拉起
    from .runtime import ensure_git_env, install_git_subprocess_prep
    ensure_git_env()              # spawn 前设好 DTM_GIT,子进程经 os.environ 继承
    install_git_subprocess_prep() # frozen+win:撤销 PyInstaller DLL 污染(治内置 git 0xc0000142)
    d = Daemon()
    d._inst_fd = fd               # 全程持有,fd 一关锁就释放=守卫失效
    d.run()


if __name__ == "__main__":
    main()
