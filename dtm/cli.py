"""薄 CLI：解析参数→调 engine→人话输出。绝不写业务逻辑（留引擎，供 Phase 2 GUI 复用）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .engine.repo import GitRepo, git_available
from .engine import identity, backup, restore, meta, stats, listing
from .engine.watcher import watch
from .engine.errors import DtmError


def _need_repo(folder: Path) -> GitRepo:
    repo = GitRepo(folder)
    if not repo.is_repo():
        raise DtmError("这个文件夹还没开启版本守护，请先运行：dtm init <文件夹>")
    identity.read_identity(folder)  # 确认是 dtm 仓
    return repo


def cmd_init(folder: Path):
    if not git_available():
        raise DtmError("找不到 git 程序，无法开启守护。请先安装 git。")
    repo = GitRepo(folder)
    if not repo.is_repo():
        repo.init()
    identity.write_identity(folder)
    (folder / ".gitignore").write_text(backup.gitignore_text())
    result = backup.do_backup(repo, folder, source="auto")
    print(f"已开启版本守护：{folder}")
    print("首次纳入备份的文件：")
    for f in result.manifest:
        print(f"  · {f}")
    for w in result.warnings:
        print(f"  ⚠️ {w}")


def cmd_watch(folder: Path):
    repo = _need_repo(folder)
    print(f"正在守护：{folder}（按 Ctrl+C 停止）")

    def on_backup(r):
        if r.committed:
            print(f"  ✓ 已存档 · {len(r.manifest)} 个文件")
        for w in r.warnings:
            print(f"  ⚠️ {w}")

    observer, db, stop = watch(repo, folder, on_backup=on_backup)
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop.set()
        db.cancel()
        observer.stop()
        observer.join()
        print("\n已停止守护。")


def cmd_list(folder: Path):
    repo = _need_repo(folder)
    for r in listing.build_version_list(repo):
        line = f"[{r.version_id}] {r.when} · {r.summary}"
        if r.milestones:
            line += "  🏷 " + " ".join(r.milestones)
        if r.note:
            line += f"  · {r.note}"
        print(line)


def cmd_restore(folder: Path, version_id: str, file: str):
    repo = _need_repo(folder)
    res = restore.safe_restore(repo, folder, version_id, file)
    print(f"已把该版本另存到旁边的新文件（未改动你当前的文件）：\n  {res.restored_path}")


def cmd_tag(folder, version_id, name):
    meta.set_tag(_need_repo(folder), version_id, name)
    print(f"已标记里程碑：{name}")


def cmd_note(folder, version_id, text):
    meta.set_note(_need_repo(folder), version_id, text or "")
    print("已更新备注。" if text else "已清空备注。")


def cmd_stats(folder):
    s = stats.repo_stats(_need_repo(folder))
    print(f"历史占用：{s.git_bytes/1024/1024:.1f}MB · 版本数：{s.version_count}")


def cmd_verify(folder, version_id=None):
    from .engine.integrity import check
    from .engine.backup import _scan
    _need_repo(folder)
    # Phase 1：校验工作区现有的纳入文件（version_id 维度留接口）
    included, _t, _w = _scan(Path(folder))
    bad = []
    for rel in included:
        ok, reason = check(Path(folder) / rel)
        if not ok:
            bad.append(reason)
    if bad:
        for b in bad:
            print(f"⚠️ {b}")
        raise DtmError("发现疑似损坏的文件（见上）。")
    print("所有文件完整可打开。")


def cmd_gc(folder):
    repo = _need_repo(folder)
    repo.gc()
    print("已压缩历史占用。")


def cmd_relocate(folder: Path):
    folder = Path(folder)
    repo = GitRepo(folder)
    if not repo.is_repo():
        raise DtmError("这个文件夹里没有可认领的历史。")
    ident = identity.read_identity(folder)
    print(f"已重新认领此文件夹的历史（标识 {ident['uuid'][:8]}）。")


def cmd_daemon(args):
    from .app.daemon import main as daemon_main
    daemon_main()


def cmd_autostart(args):
    from .engine.autostart import get_autostart
    from .app.runtime import daemon_launch_command
    a = get_autostart()
    if args.action == "enable":
        a.install(daemon_launch_command())   # 收口 frozen/dev:冻结指 .app,开发指 python -m
        print("已设为开机自启。")
    elif args.action == "disable":
        a.uninstall(); print("已关闭开机自启。")
    else:
        print("开机自启:" + ("开" if a.is_enabled() else "关"))


def main(argv=None):
    from .app.runtime import ensure_git_env
    ensure_git_env()                    # 用对的 git(冻结=内置,开发=系统);runtime 轻、不拉 GUI 依赖
    p = argparse.ArgumentParser(prog="dtm", description="文档时光机（命令行版）")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").add_argument("folder")
    sub.add_parser("watch").add_argument("folder")
    sub.add_parser("list").add_argument("folder")
    r = sub.add_parser("restore")
    r.add_argument("folder")
    r.add_argument("version_id")
    r.add_argument("file")
    t = sub.add_parser("tag")
    t.add_argument("folder")
    t.add_argument("version_id")
    t.add_argument("name")
    n = sub.add_parser("note")
    n.add_argument("folder")
    n.add_argument("version_id")
    n.add_argument("text", nargs="?")
    sub.add_parser("stats").add_argument("folder")
    v = sub.add_parser("verify")
    v.add_argument("folder")
    v.add_argument("version_id", nargs="?")
    sub.add_parser("gc").add_argument("folder")
    sub.add_parser("relocate").add_argument("folder")
    sub.add_parser("daemon")                                    # 启动守护(供自启拉起)
    ast = sub.add_parser("autostart")
    ast.add_argument("action", choices=["enable", "disable", "status"])
    a = p.parse_args(argv)
    if a.cmd == "daemon":                                       # 无 folder 参数,先分流
        cmd_daemon(a); return 0
    if a.cmd == "autostart":
        cmd_autostart(a); return 0
    try:
        f = Path(a.folder)
        if a.cmd == "init":
            cmd_init(f)
        elif a.cmd == "watch":
            cmd_watch(f)
        elif a.cmd == "list":
            cmd_list(f)
        elif a.cmd == "restore":
            cmd_restore(f, a.version_id, a.file)
        elif a.cmd == "tag":
            cmd_tag(f, a.version_id, a.name)
        elif a.cmd == "note":
            cmd_note(f, a.version_id, a.text)
        elif a.cmd == "stats":
            cmd_stats(f)
        elif a.cmd == "verify":
            cmd_verify(f, a.version_id)
        elif a.cmd == "gc":
            cmd_gc(f)
        elif a.cmd == "relocate":
            cmd_relocate(f)
        return 0
    except DtmError as e:
        print(f"⚠️ {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
