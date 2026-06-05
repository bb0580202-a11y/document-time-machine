import datetime
from dtm.engine.treemap import RawCommit, Node, order_by_ancestry, assign_lanes, find_clusters, find_gaps, choose_step, ruler_ticks, build_treemap, treemap_to_dict


def _rc(cid, parents, t):
    return RawCommit(full_id=cid, parents=parents, unix_time=t,
                     iso_time="2026-06-01T00:00:00", note="", milestones=[],
                     delta_sign="flat")


def test_order_follows_ancestry_not_clock():
    # 子节点的时间戳比父节点更早(时钟错乱),排序仍须 父在前、子在后
    c1 = _rc("a", [], 100)
    c2 = _rc("b", ["a"], 50)   # 时间更早,但它是 a 的孩子
    c3 = _rc("c", ["b"], 70)
    out = [c.full_id for c in order_by_ancestry([c3, c2, c1])]
    assert out == ["a", "b", "c"]


def test_order_tiebreaks_by_time_among_roots():
    a = _rc("a", [], 200)
    b = _rc("b", [], 100)      # 两个根,时间小的在前
    out = [c.full_id for c in order_by_ancestry([a, b])]
    assert out == ["b", "a"]


def test_order_empty_input():
    assert order_by_ancestry([]) == []


def test_order_single_node():
    a = _rc("a", [], 10)
    assert [c.full_id for c in order_by_ancestry([a])] == ["a"]


def test_order_fork_one_parent_two_children():
    a = _rc("a", [], 10)
    b = _rc("b", ["a"], 30)
    c = _rc("c", ["a"], 20)
    # a 先;a 之后两个孩子按时间 tie-break:c(20) 在 b(30) 前
    out = [x.full_id for x in order_by_ancestry([a, b, c])]
    assert out == ["a", "c", "b"]


def test_main_chain_is_lane_zero_branch_gets_own_lane():
    # 主线 a<-b<-c;分支 alt 从 a 岔出:a<-x<-y
    a = _rc("a", [], 10)
    b = _rc("b", ["a"], 20)
    c = _rc("c", ["b"], 30)
    x = _rc("x", ["a"], 25)
    y = _rc("y", ["x"], 35)
    lane_of, names = assign_lanes([a, b, c, x, y],
                                  {"main": "c", "alt": "y"}, "main")
    assert lane_of["a"] == 0 and lane_of["b"] == 0 and lane_of["c"] == 0
    assert lane_of["x"] == 1 and lane_of["y"] == 1
    assert names[0] == "main" and names[1] == "alt"


def test_two_branches_from_main_get_distinct_lanes():
    a = _rc("a", [], 10)
    b = _rc("b", ["a"], 20)
    x1 = _rc("x1", ["a"], 25)
    x2 = _rc("x2", ["a"], 26)
    lane_of, names = assign_lanes(
        [a, b, x1, x2],
        {"main": "b", "alt1": "x1", "alt2": "x2"}, "main")
    assert lane_of["x1"] == 1 and lane_of["x2"] == 2     # 不撞列
    assert names[1] == "alt1" and names[2] == "alt2"


def test_branch_off_a_branch_does_not_collapse():
    a = _rc("a", [], 10)
    b = _rc("b", ["a"], 20)
    x = _rc("x", ["a"], 25)        # alt 从主线岔出
    y = _rc("y", ["x"], 35)
    z = _rc("z", ["x"], 40)        # alt-nested 从 alt 的 x 再岔出
    lane_of, names = assign_lanes(
        [a, b, x, y, z],
        {"main": "b", "alt": "y", "alt-nested": "z"}, "main")
    assert lane_of["x"] == 1 and lane_of["y"] == 1       # alt 在 lane1
    assert lane_of["z"] == 2                              # 嵌套分支拿 lane2,不塌回


def _node(cid, t, lane=0, note="", milestones=None, current=False):
    return Node(version_id=cid[:8], full_id=cid, unix_time=t,
                iso_time="2026-06-01T00:00:00", lane=lane, title="", note=note,
                milestones=milestones or [], delta_sign="flat",
                is_current=current, is_branch_point=False)


def test_burst_within_gap_collapses_into_one_cluster():
    nodes = [_node(f"n{i}", 1000 + i * 10) for i in range(5)]  # 5 个,间隔 10s
    clusters = find_clusters(nodes, gap_seconds=60, min_run=3)
    assert len(clusters) == 1
    assert clusters[0].count == 5


def test_spaced_nodes_do_not_cluster():
    nodes = [_node("a", 0), _node("b", 5000), _node("c", 10000)]  # 间隔大
    assert find_clusters(nodes, gap_seconds=60, min_run=3) == []


def test_significant_node_breaks_the_run():
    nodes = [_node("a", 0), _node("b", 10),
             _node("m", 20, milestones=["★"]),   # 里程碑打断
             _node("c", 30), _node("d", 40)]
    # 两段普通各 2 个 < min_run=3 → 不成簇
    assert find_clusters(nodes, gap_seconds=60, min_run=3) == []


def test_exactly_min_run_forms_cluster():
    # 恰好 3 个(min_run 下边界)→ 成簇
    nodes = [_node("a", 0), _node("b", 10), _node("c", 20)]
    clusters = find_clusters(nodes, gap_seconds=60, min_run=3)
    assert len(clusters) == 1 and clusters[0].count == 3


def test_gap_exactly_threshold_is_not_close():
    # 间隔恰好 == gap_seconds → 判定用严格 < ,不算密集,不聚
    nodes = [_node("a", 0), _node("b", 120), _node("c", 240)]
    assert find_clusters(nodes, gap_seconds=120, min_run=3) == []


def test_protect_ends_keeps_first_and_last_out_of_cluster():
    # 5 个密集普通节点;protect_ends → 首版/末版不入簇,只折中间 3 个(始末锚点保持可见)
    nodes = [_node(f"n{i}", 1000 + i * 10) for i in range(5)]
    clusters = find_clusters(nodes, gap_seconds=60, min_run=3, protect_ends=True)
    assert len(clusters) == 1 and clusters[0].count == 3
    assert nodes[0].full_id not in clusters[0].node_ids   # 初始版不折
    assert nodes[-1].full_id not in clusters[0].node_ids  # 末版不折


def test_branch_point_breaks_the_run():
    # 分叉点是重要锚点,打断密集 run(不参与折叠)
    nodes = [_node("a", 0), _node("b", 10), _node("c", 20), _node("d", 30), _node("e", 40)]
    nodes[2].is_branch_point = True
    # c 是分叉点 → 切成 a,b(2个) 和 d,e(2个),各 < min_run=3 → 不成簇
    assert find_clusters(nodes, gap_seconds=60, min_run=3) == []


DAY = 86400


def test_long_idle_becomes_gap():
    nodes = [_node("a", 0), _node("b", 9 * DAY)]
    gaps = find_gaps(nodes, idle_seconds=2 * DAY)
    assert len(gaps) == 1
    assert gaps[0].after_id == "a"
    assert gaps[0].days == 9


def test_close_nodes_no_gap():
    nodes = [_node("a", 0), _node("b", 3600)]
    assert find_gaps(nodes, idle_seconds=2 * DAY) == []


def test_gap_exactly_two_days_is_not_a_gap():
    # 恰好 2 天 → 用严格 > ,不算空白
    nodes = [_node("a", 0), _node("b", 2 * DAY)]
    assert find_gaps(nodes, idle_seconds=2 * DAY) == []


def test_gap_just_over_two_days_is_a_gap():
    nodes = [_node("a", 0), _node("b", 2 * DAY + 3600)]  # 2 天零 1 小时
    gaps = find_gaps(nodes, idle_seconds=2 * DAY)
    assert len(gaps) == 1 and gaps[0].after_id == "a"
    assert gaps[0].days == 2     # floor((2d+1h)/1d) = 2


def test_multiple_gaps_each_detected():
    nodes = [_node("a", 0), _node("b", 5 * DAY),
             _node("c", 5 * DAY + 3600), _node("d", 15 * DAY)]
    gaps = find_gaps(nodes, idle_seconds=2 * DAY)
    # a->b 5天=空白;b->c 1小时=否;c->d ~10天=空白
    assert [g.after_id for g in gaps] == ["a", "c"]
    assert gaps[0].days == 5


def test_no_gap_with_single_or_empty():
    # find_gaps 只看相邻节点对:没有"开头/结尾"幻影空白
    assert find_gaps([], idle_seconds=2 * DAY) == []
    assert find_gaps([_node("a", 0)], idle_seconds=2 * DAY) == []


def test_choose_step_adapts_to_span():
    assert choose_step(6 * 3600) == ("hour", 3)
    assert choose_step(10 * DAY) == ("day", 2)
    assert choose_step(60 * DAY) == ("week", 1)
    assert choose_step(200 * DAY) == ("month", 1)


def test_choose_step_unit_boundaries():
    # 四个粒度边界各钉死(<= 上界归低粒度,+1 跳高粒度)
    assert choose_step(4 * DAY) == ("hour", 12)
    assert choose_step(4 * DAY + 1) == ("day", 2)
    assert choose_step(21 * DAY) == ("day", 2)
    assert choose_step(21 * DAY + 1) == ("week", 1)
    assert choose_step(90 * DAY) == ("week", 1)
    assert choose_step(90 * DAY + 1) == ("month", 1)
    assert choose_step(1095 * DAY) == ("month", 3)
    assert choose_step(1095 * DAY + 1) == ("year", 1)


def test_very_long_span_falls_back_to_year_not_explode():
    assert choose_step(3650 * DAY + 1) == ("year", 2)        # >10年 → 双年
    start = int(datetime.datetime(2000, 1, 1).timestamp())
    end = int(datetime.datetime(2020, 1, 1).timestamp())     # 20 年
    ticks = ruler_ticks(start, end)
    assert len(ticks) <= 16                                  # 刻度不爆炸
    isos = [t.iso for t in ticks]
    assert isos == sorted(isos)


def test_ruler_ticks_ascending_and_nonempty():
    start = int(datetime.datetime(2026, 5, 20, 9, 0).timestamp())
    end = int(datetime.datetime(2026, 6, 2, 18, 0).timestamp())   # 约 13 天
    ticks = ruler_ticks(start, end)
    assert len(ticks) >= 2
    isos = [t.iso for t in ticks]
    assert isos == sorted(isos)


def test_week_ticks_align_to_monday_not_first_version():
    start = int(datetime.datetime(2026, 5, 20, 15, 0).timestamp())  # week 粒度
    end = int(datetime.datetime(2026, 7, 10).timestamp())            # 约 51 天
    first = datetime.datetime.fromisoformat(ruler_ticks(start, end)[0].iso)
    assert first.weekday() == 0       # 周一对齐,而非从首版硬切


def test_month_ticks_align_to_month_start():
    start = int(datetime.datetime(2026, 3, 15).timestamp())
    end = int(datetime.datetime(2026, 11, 15).timestamp())   # 约 8 个月
    first = datetime.datetime.fromisoformat(ruler_ticks(start, end)[0].iso)
    assert first.day == 1


def test_zero_span_no_crash_no_infinite_loop():
    t = 1_700_000_000
    ticks = ruler_ticks(t, t)
    assert isinstance(ticks, list) and len(ticks) >= 1


def test_build_treemap_titles_lanes_current_and_branchpoint():
    a = _rc("aaaaaaaa1", [], 10)
    b = _rc("bbbbbbbb1", ["aaaaaaaa1"], 20); b.note = "导师说结论太弱"
    x = _rc("xxxxxxxx1", ["aaaaaaaa1"], 25)   # 从 a 岔出
    tm = build_treemap([a, b, x],
                       branch_tips={"main": "bbbbbbbb1", "alt": "xxxxxxxx1"},
                       main_branch="main", current_id="bbbbbbbb1")
    by = {n.full_id: n for n in tm.nodes}
    # 有备注→备注当标题;无备注→绝对时间到分
    assert by["bbbbbbbb1"].title == "导师说结论太弱"
    assert by["aaaaaaaa1"].title == "2026-06-01 00:00"
    # 当前版本
    assert by["bbbbbbbb1"].is_current is True
    # a 岔出了 alt 泳道 → branch point
    assert by["aaaaaaaa1"].is_branch_point is True
    # 泳道:main=0 不折叠;alt=1
    lanes = {l.index: l for l in tm.lanes}
    assert lanes[0].collapsed is False
    assert lanes[1].name == "alt"


def test_to_dict_is_json_serializable():
    import json
    a = _rc("a", [], 10)
    tm = build_treemap([a], {"main": "a"}, "main", "a")
    json.dumps(treemap_to_dict(tm))   # 不抛即可


def test_node_parents_present_in_dict():
    # 前端要靠 parents 画跨泳道的岔路连线
    a = _rc("a", [], 10)
    b = _rc("b", ["a"], 20)
    d = treemap_to_dict(build_treemap([a, b], {"main": "b"}, "main", "b"))
    by = {n["full_id"]: n for n in d["nodes"]}
    assert by["b"]["parents"] == ["a"]
    assert by["a"]["parents"] == []
