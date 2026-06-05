"""仓库自检:逮断电打断 commit 导致的 HEAD/最近一笔损坏(断电最常见的损伤)。

便宜检查、非完整 `git fsck`——逮"最近一笔/HEAD 坏了",逮不到"历史深处某个 blob 悄坏"
(全量 fsck 每次启动太贵)。故告警文案用"可能/应该"hedge,不把便宜检查吹成完整保证。
只检测+告警,绝不自动修复(修坏 HEAD = 动历史、擦边 INV-1,单独评审轮)。"""
from __future__ import annotations

from .repo import GitRepo
from .errors import DtmError

_CORRUPT_REASON = (
    "这个文件夹的版本历史好像有一处损坏了（也许上次保存时电脑突然关机）。"
    "之前的历史版本应该都还在——建议先把整个文件夹拷一份备份。"
)


def check_repo(repo: GitRepo) -> tuple[bool, str]:
    """返回 (ok, reason)。ok=True→reason 空。ok=False→reason 是给用户的人话告警。
    没 .git 不归"损坏"管(夹没了/没初始化是另一类,由 registry status 处理)→视为 ok。"""
    if not repo.is_repo():
        return True, ""
    try:
        repo.head()                       # rev-parse HEAD:HEAD/ref 解析得开
        repo.log("-1")                    # 读 HEAD 那笔 commit 对象:坏了/缺了会抛
        repo.files_changed("HEAD")        # 走一遍 HEAD 的树(--name-only):树对象在
    except DtmError:
        return False, _CORRUPT_REASON     # 任一失败=判坏,返回人话、绝不自己崩
    return True, ""


_DEEP_CORRUPT_REASON = (
    "深度体检发现版本历史里有数据损坏了（可能是硬盘坏块）。请立刻把整个文件夹"
    "拷一份到别的硬盘 / U 盘——个别版本也许已经救不回，但拷走的副本能保住其余完好的历史。"
)


def deep_check(repo: GitRepo) -> tuple[bool, str]:
    """全量 fsck：在出事前逮住"历史深处的坏块"——check_repo 只看 HEAD，逮不到。
    比 check_repo 贵（要读全部对象），故只在守护后台空闲时低频跑，绝不进开窗热路径。
    只检测 + 告警，绝不自动修（动历史擦 INV-1 边，留单独评审轮）。"""
    if not repo.is_repo():
        return True, ""
    try:
        rc, _out = repo.fsck()
    except DtmError:
        return False, _DEEP_CORRUPT_REASON   # fsck 本身跑不起来也按"可能坏"处理
    if rc != 0:
        return False, _DEEP_CORRUPT_REASON
    return True, ""
