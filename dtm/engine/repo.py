"""GitRepo：所有 git 操作的唯一入口。subprocess 调系统 git CLI（禁 pygit2）。"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import probe
from .errors import GitUnavailableError, DtmError
from .git_exe import (  # noqa: F401 (git_path/git_available 对外重导出，cli/测试在用)
    git_path, git_available, subprocess_prep, subprocess_kwargs,
)


@dataclass
class LogEntry:
    commit_id: str
    iso_time: str          # 提交者时间 ISO8601
    unix_time: int
    message: str           # commit subject
    parents: list[str]


class GitRepo:
    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def _git(self, *args: str, check=True, capture=True) -> subprocess.CompletedProcess:
        if not git_available():
            raise GitUnavailableError(
                "找不到 git 程序，无法做版本备份。请先安装 git 后重试。"
            )
        _t = time.perf_counter()
        try:
            with subprocess_prep():   # frozen+win:撤销 PyInstaller DLL 污染(治内置 git 0xc0000142)
                return subprocess.run(
                    [git_path(), "-C", str(self.folder), *args],
                    check=check, capture_output=capture, text=True,
                    encoding="utf-8", errors="replace",   # 强制 UTF-8:中文 Windows 默认 GBK 会解坏 git 的 UTF-8 输出
                    **subprocess_kwargs(),   # win:CREATE_NO_WINDOW 不闪黑窗
                )
        except subprocess.CalledProcessError as e:
            raise DtmError(f"操作失败：{(e.stderr or e.stdout or '').strip()}") from e
        finally:
            probe.record_git(args, time.perf_counter() - _t)   # 性能探针:记这次 git 调用耗时

    def init(self) -> None:
        self._git("init", "-q")
        # 锁死本地身份与安全/编码相关设置；绝不设 remote（INV-4）
        self._git("config", "user.name", "doc-time-machine")
        self._git("config", "user.email", "dtm@localhost")
        self._git("config", "commit.gpgsign", "false")
        self._git("config", "core.precomposeunicode", "true")  # macOS NFD→NFC
        self._git("config", "core.quotepath", "false")  # 中文文件名不转义，人类可读
        self._git("config", "core.filemode", "false")    # 跨盘搬家(exFAT/FAT32 无权限位)不刷虚假改动
        self._git("config", "core.autocrlf", "false")    # 跨平台不改行尾(docx 二进制,保护文本文件)
        self._git("config", "gc.auto", "0")  # 由我们显式控制 gc

    def is_repo(self) -> bool:
        return (self.folder / ".git").is_dir()

    def add_all(self) -> None:
        self._git("add", "-A")

    def has_staged_changes(self) -> bool:
        r = self._git("diff", "--cached", "--quiet", check=False)
        return r.returncode != 0

    def commit(self, message: str) -> str:
        self._git("commit", "-q", "-m", message, "--allow-empty-message")
        return self._git("rev-parse", "HEAD").stdout.strip()

    def head(self) -> str:
        """当前 HEAD 的完整 commit id(用户此刻所在的版本)。"""
        return self._git("rev-parse", "HEAD").stdout.strip()

    def log(self, ref: str = "--branches") -> list[LogEntry]:
        # 默认 --branches：列出所有路线(分支)，但排除 notes/tags 等内部 ref，
        # 否则加一条备注会污染出一个假"版本"。
        fmt = "%H%x1f%cI%x1f%ct%x1f%P%x1f%s"
        out = self._git("log", ref, f"--format={fmt}").stdout or ""   # 防御:stdout None 不崩(空→无版本)
        entries = []
        for line in out.splitlines():
            if not line.strip():
                continue
            cid, iso, ct, parents, subj = line.split("\x1f", 4)
            entries.append(LogEntry(cid, iso, int(ct), subj,
                                    parents.split() if parents else []))
        return entries

    def show_file(self, commit_id: str, rel_path: str) -> bytes:
        # 取二进制 blob，故绕开 _git 的 text 解码；但错误必须同样翻成人话(INV-5/6)：
        # 这是"还原取数据"的唯一入口，失败=用户正举着救命稻草，绝不能漏天书。
        if not git_available():
            raise GitUnavailableError(
                "找不到 git 程序，无法读取历史版本。请先安装 git 后重试。"
            )
        try:
            with subprocess_prep():
                r = subprocess.run(
                    [git_path(), "-C", str(self.folder), "show", f"{commit_id}:{rel_path}"],
                    capture_output=True, check=True, **subprocess_kwargs(),
                )
        except subprocess.CalledProcessError as e:
            name = Path(rel_path).name
            raise DtmError(
                f"这一版的「{name}」读不出来了——它的历史数据可能已损坏"
                f"（例如硬盘坏块）。这一版恐怕找不回了，但你其它版本通常不受影响，"
                f"请试试还原相邻的版本。"
            ) from e
        return r.stdout

    def files_changed(self, commit_id: str) -> list[str]:
        out = self._git("show", "--name-only", "--format=", commit_id).stdout
        return [l for l in out.splitlines() if l.strip()]

    def blob_size(self, commit_id: str, rel_path: str) -> int | None:
        """该版里此文件的字节数;该版无此文件(或 ref 不存在,如首版的父)返回 None。
        用 cat-file -s 取 blob 大小,绕开 numstat 对二进制文件返回 '-' 的坑。"""
        r = self._git("cat-file", "-s", f"{commit_id}:{rel_path}", check=False)
        if r.returncode != 0:
            return None
        try:
            return int(r.stdout.strip())
        except ValueError:
            return None

    def changed_files_map(self, ref: str = "--branches") -> dict[str, list[str]]:
        """一次取每个版本改了哪些文件(git log --name-only),省每版一次 spawn(治卡顿)。
        %x1e 记录分隔、首行=版本 id、其后为文件名。"""
        out = self._git("log", ref, "--name-only", "--format=%x1e%H").stdout or ""
        result: dict[str, list[str]] = {}
        for rec in out.split("\x1e"):
            lines = [l for l in rec.splitlines() if l.strip()]
            if lines:
                result[lines[0].strip()] = lines[1:]
        return result

    def batch_blob_sizes(self, specs: list[str]) -> dict[str, int]:
        """一次问多个 <rev>:<path> 的 blob 字节数(git cat-file --batch-check),
        替代每文件两次 cat-file spawn(Windows 卡顿大头)。不存在的 spec 不进结果。"""
        if not specs:
            return {}
        with subprocess_prep():
            r = subprocess.run(
                [git_path(), "-C", str(self.folder), "cat-file",
                 "--batch-check=%(objecttype) %(objectsize)"],
                input="\n".join(specs) + "\n",
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                **subprocess_kwargs(),
            )
        sizes: dict[str, int] = {}
        for spec, line in zip(specs, (r.stdout or "").splitlines()):
            parts = line.split()
            if len(parts) == 2 and parts[0] == "blob":   # 否则 "missing" 等→跳过(=None)
                sizes[spec] = int(parts[1])
        return sizes

    def create_branch(self, name: str, start_commit: str) -> None:
        self._git("branch", name, start_commit)

    def checkout(self, ref: str) -> None:
        self._git("checkout", "-q", ref)

    def current_branch(self) -> str:
        return self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    def branches(self) -> dict[str, str]:
        """返回 {分支名: 该分支 tip 的完整 commit id}。"""
        out = self._git(
            "for-each-ref", "--format=%(refname:short) %(objectname)",
            "refs/heads",
        ).stdout
        result = {}
        for line in out.splitlines():
            if line.strip():
                name, cid = line.rsplit(" ", 1)
                result[name.strip()] = cid.strip()
        return result

    def gc(self) -> None:
        self._git("gc", "--aggressive", "--quiet")

    def fsck(self) -> tuple[int, str]:
        """全量 git fsck：重算每个对象的 SHA-1，能逮"历史深处某个 blob 悄悄坏掉"
        （连通性检查 --connectivity-only 逮不到，因坏块后对象仍可达，只是内容变了）。
        返回 (returncode, 合并输出)。check=False：有坏对象时 git 返回非 0，不抛、交调用方判。
        贵（要读全部对象）→ 只在守护后台低频跑，不进开窗热路径。"""
        r = self._git("fsck", "--no-progress", "--no-dangling", check=False)
        return r.returncode, ((r.stderr or "") + (r.stdout or "")).strip()
