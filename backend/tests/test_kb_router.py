"""KBRouter 单元测试

测试知识库的列表扫描、空路径、隐藏目录过滤等。
"""

from pathlib import Path

import pytest

from core.kb_router import (
    list_knowledge_bases,
    _build_kb_catalog,
    _read_index_preview,
)


class TestListKnowledgeBases:
    """list_knowledge_bases 测试"""

    def test_empty_root(self, tmp_kb_dir: Path):
        """知识库根目录不存在时应返回空列表"""
        non_existent = Path("/tmp/nonexistent_path_for_test")  # noqa: S108
        if non_existent.exists():
            pytest.skip("Path unexpectedly exists")
        result = list_knowledge_bases(knowledge_root=non_existent)
        assert result == []

    def test_empty_directory(self, tmp_kb_dir: Path):
        """空目录应返回空列表"""
        result = list_knowledge_bases(knowledge_root=tmp_kb_dir)
        assert result == []

    def test_single_kb(self, tmp_kb_dir: Path):
        """应识别一级子目录"""
        (tmp_kb_dir / "AnswerAgent").mkdir()
        result = list_knowledge_bases(knowledge_root=tmp_kb_dir)
        assert result == ["AnswerAgent"]

    def test_multiple_kbs_sorted(self, tmp_kb_dir: Path):
        """多个知识库应按字母序返回"""
        for name in ["zzz", "aaa", "mmm"]:
            (tmp_kb_dir / name).mkdir()
        result = list_knowledge_bases(knowledge_root=tmp_kb_dir)
        assert result == ["aaa", "mmm", "zzz"]

    def test_hidden_directories_ignored(self, tmp_kb_dir: Path):
        """以 '.' 开头的目录应被忽略"""
        (tmp_kb_dir / ".hidden").mkdir()
        (tmp_kb_dir / "visible").mkdir()
        result = list_knowledge_bases(knowledge_root=tmp_kb_dir)
        assert ".hidden" not in result
        assert "visible" in result

    def test_files_ignored(self, tmp_kb_dir: Path):
        """普通文件不应被当作知识库"""
        (tmp_kb_dir / "file.md").write_text("test", encoding="utf-8")
        result = list_knowledge_bases(knowledge_root=tmp_kb_dir)
        assert result == []

    def test_mixed_files_and_dirs(self, tmp_kb_dir: Path):
        """混合文件和目录时只返回目录"""
        (tmp_kb_dir / "readme.md").write_text("test", encoding="utf-8")
        (tmp_kb_dir / "kb1").mkdir()
        (tmp_kb_dir / "kb2").mkdir()
        result = list_knowledge_bases(knowledge_root=tmp_kb_dir)
        assert "readme.md" not in result
        assert result == ["kb1", "kb2"]


class TestIndexPreview:
    """_read_index_preview 测试"""

    def test_no_index_file(self, tmp_kb_dir: Path):
        """无索引文件应返回空字符串"""
        (tmp_kb_dir / "kb").mkdir()
        result = _read_index_preview(tmp_kb_dir / "kb")
        assert result == ""

    def test_chinese_index(self, tmp_kb_dir: Path):
        """应正确读取中文索引.md"""
        kb_root = tmp_kb_dir / "kb"
        kb_root.mkdir()
        (kb_root / "索引.md").write_text(
            "# 测试知识库\n\n包含 SSE 协议相关文档。",
            encoding="utf-8",
        )
        result = _read_index_preview(kb_root)
        assert "测试知识库" in result
        assert "SSE" in result

    def test_english_index(self, tmp_kb_dir: Path):
        """应兼容英文 index.md"""
        kb_root = tmp_kb_dir / "kb"
        kb_root.mkdir()
        (kb_root / "index.md").write_text("# Test KB\n\nDocs about SSE.", encoding="utf-8")
        result = _read_index_preview(kb_root)
        assert "Test KB" in result

    def test_index_priority(self, tmp_kb_dir: Path):
        """索引.md 优先于 index.md"""
        kb_root = tmp_kb_dir / "kb"
        kb_root.mkdir()
        (kb_root / "索引.md").write_text("# 中文索引", encoding="utf-8")
        (kb_root / "index.md").write_text("# English Index", encoding="utf-8")
        result = _read_index_preview(kb_root)
        assert "中文索引" in result
        assert "English" not in result

    def test_truncated_long_index(self, tmp_kb_dir: Path):
        """超长索引应被截断"""
        kb_root = tmp_kb_dir / "kb"
        kb_root.mkdir()
        # 写入超过限制的内容（默认 2000 字符）
        long_content = "# " + "x" * 3000
        (kb_root / "索引.md").write_text(long_content, encoding="utf-8")
        result = _read_index_preview(kb_root)
        assert len(result) < 2500  # 被截断
        assert result.endswith("...(truncated)")


class TestBuildCatalog:
    """_build_kb_catalog 测试"""

    def test_empty_candidates(self, tmp_kb_dir: Path):
        """空候选列表应返回空字符串"""
        result = _build_kb_catalog([], tmp_kb_dir)
        assert result == ""

    def test_kb_without_index(self, tmp_kb_dir: Path):
        """无索引的知识库应标记为无描述"""
        (tmp_kb_dir / "kb1").mkdir()
        result = _build_kb_catalog(["kb1"], tmp_kb_dir)
        assert "无 索引.md" in result

    def test_kb_with_index(self, tmp_kb_dir: Path):
        """有索引的知识库应展示索引预览"""
        kb_root = tmp_kb_dir / "kb1"
        kb_root.mkdir()
        (kb_root / "索引.md").write_text("# KB1 文档\n\n包含 SSE 内容。", encoding="utf-8")
        result = _build_kb_catalog(["kb1"], tmp_kb_dir)
        assert "KB1 文档" in result
        assert "SSE" in result
