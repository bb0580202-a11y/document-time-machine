from dtm.engine.integrity import check


def test_good_docx_ok(folder, make_docx_factory):
    p = make_docx_factory(folder / "ok.docx", "hi")
    ok, reason = check(p)
    assert ok is True and reason == ""


def test_corrupt_docx_detected(folder):
    bad = folder / "bad.docx"
    bad.write_bytes(b"this is not a zip")
    ok, reason = check(bad)
    assert ok is False and "损坏" in reason


def test_non_office_skipped(folder):
    t = folder / "note.txt"
    t.write_text("hi")
    ok, reason = check(t)
    assert ok is True  # 非 zip/pdf 直接跳过校验
