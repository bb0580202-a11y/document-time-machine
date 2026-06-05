"""版本树布局计算:把 git 历史算成渲染就绪结构。纯逻辑,无副作用。
顺序以父子链(DAG)为准,不靠系统时钟 —— 时钟错乱/跨时区也不会乱序。"""
from __future__ import annotations
import datetime
import heapq
from collections import defaultdict
from dataclasses import dataclass, asdict, field

from .messages import parse_message
from . import meta


@dataclass
class RawCommit:
    full_id: str
    parents: list[str]
    unix_time: int
    iso_time: str
    note: str
    milestones: list[str]
    delta_sign: str


@dataclass
class Node:
    version_id: str
    full_id: str
    unix_time: int
    iso_time: str
    lane: int
    title: str
    note: str
    milestones: list[str]
    delta_sign: str
    is_current: bool
    is_branch_point: bool
    parents: list[str] = field(default_factory=list)  # 前端画跨泳道岔路连线用


@dataclass
class Cluster:
    lane: int
    count: int
    start_iso: str
    end_iso: str
    node_ids: list[str]


@dataclass
class Gap:
    after_id: str
    days: int


@dataclass
class Tick:
    iso: str
    label: str


@dataclass
class Lane:
    index: int
    name: str
    collapsed: bool
    summary: str


@dataclass
class TreeMap:
    nodes: list[Node]
    lanes: list[Lane]
    clusters: list[Cluster]
    gaps: list[Gap]
    ticks: list[Tick]


def order_by_ancestry(commits: list[RawCommit]) -> list[RawCommit]:
    """拓扑排序(父在前),同层 tie-break 用 unix_time 再 full_id。无合并→链/树。"""
    by_id = {c.full_id: c for c in commits}
    indeg = {c.full_id: 0 for c in commits}
    children: dict[str, list[str]] = defaultdict(list)
    for c in commits:
        for p in c.parents:
            if p in by_id:
                children[p].append(c.full_id)
                indeg[c.full_id] += 1
    ready = [(by_id[i].unix_time, i) for i, d in indeg.items() if d == 0]
    heapq.heapify(ready)
    out: list[RawCommit] = []
    while ready:
        _, i = heapq.heappop(ready)
        out.append(by_id[i])
        for ch in children[i]:
            indeg[ch] -= 1
            if indeg[ch] == 0:
                heapq.heappush(ready, (by_id[ch].unix_time, ch))
    return out


def _ancestry(tip: str, by_id: dict) -> list[str]:
    """tip 及其所有祖先(沿 parents)。dtm 无合并,链状。"""
    out, stack, seen = [], [tip], set()
    while stack:
        cur = stack.pop()
        if cur not in by_id or cur in seen:
            continue
        seen.add(cur)
        out.append(cur)
        stack.extend(by_id[cur].parents)
    return out


def assign_lanes(commits: list[RawCommit], branch_tips: dict[str, str],
                 main_branch: str) -> tuple[dict[str, int], dict[int, str]]:
    """返回 (commit_id->lane, lane->分支名)。主线 lane 0,其余分支按名字排序各占一条。"""
    by_id = {c.full_id: c for c in commits}
    lane_of: dict[str, int] = {}
    names: dict[int, str] = {}
    main_tip = branch_tips.get(main_branch)
    if main_tip:
        names[0] = main_branch
        for cid in _ancestry(main_tip, by_id):
            lane_of[cid] = 0
    nxt = 1
    for name in sorted(k for k in branch_tips if k != main_branch):
        exclusive = [cid for cid in _ancestry(branch_tips[name], by_id)
                     if cid not in lane_of]
        if not exclusive:
            continue
        names[nxt] = name
        for cid in exclusive:
            lane_of[cid] = nxt
        nxt += 1
    for c in commits:               # 兜底
        lane_of.setdefault(c.full_id, 0)
    names.setdefault(0, main_branch)
    return lane_of, names


def find_clusters(lane_nodes: list[Node], gap_seconds: float,
                  min_run: int = 3, protect_ends: bool = False) -> list[Cluster]:
    """同一泳道、时间升序。把连续'平凡节点'、相邻间隔 < gap_seconds、
    长度 >= min_run 的一段,聚合成一个簇。
    平凡 = 非里程碑/非备注/非当前/非分叉点(都是重要锚点,不折)。
    protect_ends=True 时,该泳道的首版(最早)与末版(最新)也永不入簇(始末锚点保持可见)。"""
    clusters: list[Cluster] = []
    run: list[Node] = []
    last_idx = len(lane_nodes) - 1

    def flush():
        if len(run) >= min_run:
            clusters.append(Cluster(
                lane=run[0].lane, count=len(run),
                start_iso=run[0].iso_time, end_iso=run[-1].iso_time,
                node_ids=[n.full_id for n in run]))
        run.clear()

    prev = None
    for i, n in enumerate(lane_nodes):
        significant = bool(n.milestones or n.note or n.is_current or n.is_branch_point)
        is_end = protect_ends and (i == 0 or i == last_idx)
        plain = not significant and not is_end
        close = prev is not None and (n.unix_time - prev.unix_time) < gap_seconds
        if plain and (not run or close):
            run.append(n)
        else:
            flush()
            if plain:
                run.append(n)
        prev = n
    flush()
    return clusters


def find_gaps(lane_nodes: list[Node], idle_seconds: float) -> list[Gap]:
    gaps: list[Gap] = []
    for a, b in zip(lane_nodes, lane_nodes[1:]):
        delta = b.unix_time - a.unix_time
        if delta > idle_seconds:
            gaps.append(Gap(after_id=a.full_id, days=int(delta // 86400)))
    return gaps


def choose_step(span_seconds: float) -> tuple[str, int]:
    """按总跨度自动选(单位, 步长),让刻度数维持在 ~4~13 个,>10 年也不爆炸。"""
    d = 86400
    if span_seconds <= 1 * d:
        return ("hour", 3)
    if span_seconds <= 4 * d:
        return ("hour", 12)
    if span_seconds <= 21 * d:
        return ("day", 2)
    if span_seconds <= 90 * d:
        return ("week", 1)
    if span_seconds <= 365 * d:
        return ("month", 1)
    if span_seconds <= 1095 * d:     # 1~3 年:季度
        return ("month", 3)
    if span_seconds <= 3650 * d:     # 3~10 年:年
        return ("year", 1)
    return ("year", 2)               # >10 年:双年(封顶,不爆炸)


def _floor(dt: datetime.datetime, unit: str) -> datetime.datetime:
    if unit == "hour":
        return dt.replace(minute=0, second=0, microsecond=0)
    if unit == "day":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if unit == "week":
        d0 = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return d0 - datetime.timedelta(days=d0.weekday())
    if unit == "month":
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)  # year


def _advance(dt: datetime.datetime, unit: str, step: int) -> datetime.datetime:
    if unit == "hour":
        return dt + datetime.timedelta(hours=step)
    if unit == "day":
        return dt + datetime.timedelta(days=step)
    if unit == "week":
        return dt + datetime.timedelta(weeks=step)
    if unit == "month":
        m = dt.month - 1 + step
        return dt.replace(year=dt.year + m // 12, month=m % 12 + 1, day=1)
    return dt.replace(year=dt.year + step)  # year


def _label(dt: datetime.datetime, unit: str) -> str:
    if unit == "hour":
        return dt.strftime("%m-%d %H:%M")
    if unit in ("day", "week"):
        return dt.strftime("%m-%d")
    if unit == "month":
        return dt.strftime("%Y-%m")
    return dt.strftime("%Y")  # year


def ruler_ticks(min_unix: int, max_unix: int) -> list[Tick]:
    span = max(0, max_unix - min_unix)
    unit, step = choose_step(span)
    start = datetime.datetime.fromtimestamp(min_unix)
    end = datetime.datetime.fromtimestamp(max_unix)
    cur = _floor(start, unit)
    ticks: list[Tick] = []
    guard = 0
    while cur <= end and guard < 2000:
        ticks.append(Tick(iso=cur.isoformat(timespec="minutes"),
                          label=_label(cur, unit)))
        cur = _advance(cur, unit, step)
        guard += 1
    return ticks


def _abs_minute(iso_time: str) -> str:
    return iso_time[:16].replace("T", " ")   # 2026-06-01T14:30:05 → 2026-06-01 14:30


def build_treemap(commits: list[RawCommit], branch_tips: dict[str, str],
                  main_branch: str, current_id: str,
                  cluster_gap: float = 1800, min_run: int = 3,
                  idle_seconds: float = 2 * 86400) -> TreeMap:
    # cluster_gap=1800(30分钟):相邻间隔<30min、≥3次的密集存档折成一簇。
    # 阈值经 CP-1 两轮放宽:120s→300s→1800s(bb 反馈仍太苛)。配合 protect_ends + 锚点豁免,
    # 折的只是"密集的平凡自动存档",首/末版、里程碑、备注、分叉点都不折,故放宽到 30min 也安全。
    # 是产品手感旋钮,可再调。
    ordered = order_by_ancestry(commits)
    lane_of, lane_names = assign_lanes(ordered, branch_tips, main_branch)

    branch_point: set[str] = set()
    for c in ordered:
        for p in c.parents:
            if p in lane_of and lane_of[p] != lane_of[c.full_id]:
                branch_point.add(p)

    nodes: list[Node] = []
    for c in ordered:
        nodes.append(Node(
            version_id=c.full_id[:8], full_id=c.full_id, unix_time=c.unix_time,
            iso_time=c.iso_time, lane=lane_of[c.full_id],
            title=(c.note or _abs_minute(c.iso_time)), note=c.note,
            milestones=list(c.milestones), delta_sign=c.delta_sign,
            is_current=(c.full_id == current_id),
            is_branch_point=(c.full_id in branch_point),
            parents=list(c.parents)))

    clusters: list[Cluster] = []
    gaps: list[Gap] = []
    lanes: list[Lane] = []
    cur_lane = next((n.lane for n in nodes if n.is_current), 0)
    for ln in sorted({n.lane for n in nodes}):
        lane_nodes = [n for n in nodes if n.lane == ln]   # 已时间升序
        clusters += find_clusters(lane_nodes, cluster_gap, min_run, protect_ends=True)
        gaps += find_gaps(lane_nodes, idle_seconds)
        name = lane_names.get(ln, f"路线{ln}")
        collapsed = (ln != 0 and ln != cur_lane)
        last = _abs_minute(lane_nodes[-1].iso_time)[5:16] if lane_nodes else ""
        summary = f"{name} · {len(lane_nodes)}版 · 最后改{last}"
        lanes.append(Lane(index=ln, name=name, collapsed=collapsed, summary=summary))

    times = [c.unix_time for c in ordered] or [0]
    ticks = ruler_ticks(min(times), max(times))
    return TreeMap(nodes=nodes, lanes=lanes, clusters=clusters, gaps=gaps, ticks=ticks)


def treemap_to_dict(tm: TreeMap) -> dict:
    return {
        "nodes": [asdict(n) for n in tm.nodes],
        "lanes": [asdict(l) for l in tm.lanes],
        "clusters": [asdict(c) for c in tm.clusters],
        "gaps": [asdict(g) for g in tm.gaps],
        "ticks": [asdict(t) for t in tm.ticks],
    }


def _delta_sign(summary: str) -> str:
    if "(+" in summary or "(﹢" in summary:
        return "up"
    if "(-" in summary or "(−" in summary:
        return "down"
    return "flat"


def from_repo(repo, main_branch: str | None = None,
              current_id: str | None = None) -> TreeMap:
    """从 GitRepo 拉历史(--branches,排除 notes/tags)构造 TreeMap。"""
    tips = repo.branches()
    if main_branch is None:
        main_branch = repo.current_branch()
    if current_id is None:
        current_id = tips.get(main_branch, "")
    notes = meta.all_notes(repo)        # 批量取代每版 spawn(治卡顿)
    tags = meta.all_tags(repo)
    commits = []
    for e in repo.log("--branches"):
        parsed = parse_message(e.message)
        commits.append(RawCommit(
            full_id=e.commit_id, parents=e.parents, unix_time=e.unix_time,
            iso_time=e.iso_time, note=notes.get(e.commit_id, ""),
            milestones=tags.get(e.commit_id, []),
            delta_sign=_delta_sign(parsed["summary"])))
    return build_treemap(commits, tips, main_branch, current_id)
