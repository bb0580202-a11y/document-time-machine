import datetime

from dtm.engine.messages import build_message, parse_message, humanize_time


def test_build_message():
    m = build_message("2026-06-01T14:30:05", "正文.docx", +38000, "auto")
    assert m == "[dtm] 2026-06-01T14:30:05 | 正文.docx(+37KB) | auto"


def test_build_message_multi_file():
    m = build_message("2026-06-01T14:30:05", ["a.docx", "b.xlsx"], +1000, "auto")
    assert "2 个文件" in m


def test_parse_roundtrip():
    m = build_message("2026-06-01T14:30:05", "正文.docx", -2048, "manual")
    p = parse_message(m)
    assert p["source"] == "manual" and p["summary"].startswith("正文.docx")


def test_humanize_recent():
    now = datetime.datetime.now().astimezone()
    assert humanize_time(int(now.timestamp()), now=now) == "刚刚"
