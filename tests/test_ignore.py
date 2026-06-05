from dtm.engine.ignore import classify, default_gitignore


def test_lock_file_ignored():
    d = classify("~$正文.docx")
    assert d.ignored is True


def test_tmp_ignored():
    assert classify("temp.tmp").ignored is True
    assert classify("build.log").ignored is True


def test_protected_whitelist():
    d = classify("正文.docx")
    assert d.ignored is False and d.protected is True


def test_grey_area_still_backed_up():
    # 既不在黑也不在白 -> MUST 默认备份 (INV-2)
    d = classify("data.sav")
    assert d.ignored is False and d.protected is False


def test_default_gitignore_contains_lock_pattern():
    assert "~$*" in default_gitignore()
