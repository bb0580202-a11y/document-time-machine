import io
import zipfile

from dtm.engine.repo import GitRepo
from dtm.engine import flags, backup


def _repo(folder):
    repo = GitRepo(folder)
    repo.init()
    return repo


def _good_docx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<x/>")
    return buf.getvalue()


def test_corrupt_map_empty_when_no_sidecar(folder):
    assert flags.corrupt_map(_repo(folder)) == {}


def test_record_and_read_roundtrip(folder):
    repo = _repo(folder)
    flags.record_corrupt(repo, "abc123", ["论文.docx"])
    assert flags.corrupt_map(repo) == {"abc123": ["论文.docx"]}


def test_record_merges_and_dedups(folder):
    repo = _repo(folder)
    flags.record_corrupt(repo, "abc", ["a.docx"])
    flags.record_corrupt(repo, "abc", ["a.docx", "b.pdf"])   # 重复 a.docx + 新 b.pdf
    assert flags.corrupt_map(repo)["abc"] == ["a.docx", "b.pdf"]


def test_record_empty_is_noop(folder):
    repo = _repo(folder)
    flags.record_corrupt(repo, "abc", [])
    assert flags.corrupt_map(repo) == {}


def test_corrupt_map_survives_bad_json(folder):
    repo = _repo(folder)
    (folder / ".git" / "dtm_corrupt.json").write_text("not json{{", encoding="utf-8")
    assert flags.corrupt_map(repo) == {}            # 读不出不崩,当空


def test_backup_flags_corrupt_source_file(folder):
    # Word 存崩了:看着是 .docx,其实不是合法 zip → 备份照原样存,并持久标记可能损坏
    repo = _repo(folder)
    (folder / "论文.docx").write_bytes(b"PK\x03\x04 not really a zip")
    res = backup.do_backup(repo, folder, "auto")
    assert res.committed                            # INV-2:坏也照样存,不漏备
    m = flags.corrupt_map(repo)
    assert res.commit_id in m
    assert "论文.docx" in m[res.commit_id]


def test_backup_does_not_lie_about_retry(folder):
    # 旧 bug:谎称"已自动重新备份一次"且其实是空操作 → 现在绝不出现这句
    repo = _repo(folder)
    (folder / "论文.docx").write_bytes(b"corrupt")
    res = backup.do_backup(repo, folder, "auto")
    assert not any("已自动重新备份" in w for w in res.warnings)


def test_backup_good_file_not_flagged(folder):
    repo = _repo(folder)
    (folder / "论文.docx").write_bytes(_good_docx_bytes())
    res = backup.do_backup(repo, folder, "auto")
    assert res.committed
    assert flags.corrupt_map(repo) == {}            # 正常文件不被误标
