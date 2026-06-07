"""测试共享夹具和工具函数"""

import json
import sys
import tempfile
from pathlib import Path
from typing import Generator

import pytest

# 将 backend/app 加入 Python 路径，使测试能导入 core.*、models.*
_app_dir = str(Path(__file__).parent.parent / "app")
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)


@pytest.fixture
def tmp_data_dir() -> Generator[Path, None, None]:
    """创建临时数据目录（用于对话 JSON 文件）"""
    with tempfile.TemporaryDirectory(prefix="answeragent_test_data_") as d:
        yield Path(d)


@pytest.fixture
def tmp_db_path() -> Generator[str, None, None]:
    """创建临时 SQLite 数据库文件路径（用于测试对话元数据隔离）"""
    with tempfile.TemporaryDirectory(prefix="answeragent_test_db_") as d:
        yield str(Path(d) / "test.db")


@pytest.fixture
def tmp_kb_dir() -> Generator[Path, None, None]:
    """创建临时知识库根目录"""
    with tempfile.TemporaryDirectory(prefix="answeragent_test_kb_") as d:
        yield Path(d)


def create_temp_kb(kb_root: Path, name: str, files: dict[str, str]) -> Path:
    """在 kb_root 下创建一个知识库，写入指定文件

    Args:
        kb_root: 知识库根目录
        name: 知识库名称（目录名）
        files: 相对路径 -> 内容的映射

    Returns:
        Path: 知识库目录路径
    """
    kb_dir = kb_root / name
    kb_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, content in files.items():
        file_path = kb_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    return kb_dir


def create_corrupted_json(file_path: Path) -> None:
    """写入损坏的 JSON 内容到文件"""
    file_path.write_text('{"id": "abc", "title": "broken', encoding="utf-8")
