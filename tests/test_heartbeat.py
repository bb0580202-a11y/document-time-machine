from dtm.app.heartbeat import detect_gap, write_beat, read_beat


def test_detect_gap_first_run_none():
    # 首次运行,没有上次记号 → 不报(不是裸奔)
    assert detect_gap(None, now=1000.0, threshold=600) is None


def test_detect_gap_clean_shutdown_none():
    # 上次是干净退出(用户主动点退出)→ 不报,别把正常关机误当裸奔
    prev = {"ts": 0.0, "clean": True}
    assert detect_gap(prev, now=99999.0, threshold=600) is None


def test_detect_gap_unclean_over_threshold_reports():
    # 没打招呼就断了、且断得够久 → 报这段空窗(秒)
    prev = {"ts": 1000.0, "clean": False}
    gap = detect_gap(prev, now=1000.0 + 3600, threshold=600)
    assert gap == 3600


def test_detect_gap_unclean_under_threshold_none():
    # 断得很短(如重启/重登录几十秒)→ 不报,免得吵
    prev = {"ts": 1000.0, "clean": False}
    assert detect_gap(prev, now=1000.0 + 30, threshold=600) is None


def test_write_read_roundtrip(tmp_path):
    p = tmp_path / "heartbeat.json"
    write_beat(p, clean=False)
    b = read_beat(p)
    assert b is not None and b["clean"] is False and isinstance(b["ts"], (int, float))
    write_beat(p, clean=True)
    assert read_beat(p)["clean"] is True


def test_read_beat_missing_none(tmp_path):
    assert read_beat(tmp_path / "nope.json") is None
