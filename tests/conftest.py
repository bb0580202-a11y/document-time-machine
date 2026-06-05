import subprocess
from pathlib import Path

import pytest
from docx import Document


@pytest.fixture
def folder(tmp_path):
    """一个干净的临时'论文文件夹'。"""
    d = tmp_path / "thesis"
    d.mkdir()
    return d


def make_docx(path: Path, text: str = "初稿") -> Path:
    doc = Document()
    doc.add_paragraph(text)
    doc.save(path)
    return path


@pytest.fixture
def make_docx_factory():
    return make_docx


def git_log_files(repo: Path):
    """测试辅助：列出 git 历史里出现过的所有文件名（验证忽略是否生效）。"""
    out = subprocess.run(
        ["git", "-C", str(repo), "log", "--all", "--name-only", "--format="],
        capture_output=True, text=True, check=True,
    ).stdout
    return {line for line in out.splitlines() if line.strip()}
