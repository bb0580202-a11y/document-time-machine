"""PyInstaller 冻结入口(.app 启动它)。

顶层脚本没有包上下文,必须用绝对 import(daemon/cli 里的相对 import 当顶层脚本跑会炸)。
freeze_support() 必须最先调:否则 spawn 出 webview 子进程时会重跑整个 app
(冒出多个托盘/窗口,典型"打包后 fork 炸弹")。
"""
import multiprocessing as mp


def main():
    mp.freeze_support()              # 必须最先:冻结 spawn 子进程时拦截、不重跑整个 app(多托盘 fork 炸弹)
    # 🔴 必须走 daemon.main(含单实例守卫+日志+git env+subprocess_prep),
    # 不能直接 Daemon().run()——否则绕过单实例,Windows 上每次双击=一个新 daemon(实测 5 个进程/多托盘)。
    from dtm.app.daemon import main as daemon_main
    daemon_main()


if __name__ == "__main__":
    main()
