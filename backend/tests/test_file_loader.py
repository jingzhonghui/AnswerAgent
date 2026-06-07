"""FileLoader 单元测试

测试两阶段文件选取的路径安全、文件类型白名单、空知识库等边界。
"""

from pathlib import Path

import pytest

from core.file_loader import (
    PathSecurityError,
    _tokenize,
    _build_candidates,
    _score_candidates,
    _safe_resolve_in_kb,
    _iter_kb_files,
    select_and_load_files,
    FileCandidate,
)
from core.config import settings


class TestPathSecurity:
    """路径安全测试"""

    def test_safe_resolve_valid(self, tmp_kb_dir: Path):
        """合法路径应正常 resolve"""
        kb_root = create_test_file(tmp_kb_dir, "valid.md", "hello")
        p = _safe_resolve_in_kb(kb_root, kb_root / "valid.md")
        assert p.exists()
        assert p.name == "valid.md"

    def test_safe_resolve_traversal(self, tmp_kb_dir: Path):
        """路径穿越应抛出 PathSecurityError"""
        kb_root = create_test_file(tmp_kb_dir, "file.md", "hello")
        with pytest.raises(PathSecurityError):
            _safe_resolve_in_kb(kb_root, kb_root / ".." / ".." / "etc" / "passwd")

    def test_safe_resolve_absolute_outside(self, tmp_kb_dir: Path):
        """绝对路径指向 kb 外应抛出"""
        kb_root = create_test_file(tmp_kb_dir, "file.md", "hello")
        with pytest.raises(PathSecurityError):
            _safe_resolve_in_kb(kb_root, Path("/etc/passwd"))

    def test_safe_resolve_link_outside(self, tmp_kb_dir: Path):
        """符号链接指向 kb 外应抛出（Windows 可能不支持符号链接，跳过）"""
        import os
        import sys

        if sys.platform == "win32":
            # Windows 上创建符号链接需要管理员权限或开发者模式
            # 跳过此测试
            pytest.skip("Symbolic link test skipped on Windows")

        kb_root = create_test_file(tmp_kb_dir, "file.md", "hello")
        link_path = kb_root / "link.md"
        try:
            os.symlink("/etc/passwd", link_path)
            with pytest.raises(PathSecurityError):
                _safe_resolve_in_kb(kb_root, link_path)
            link_path.unlink()
        except (OSError, NotImplementedError):
            pytest.skip("Cannot create symbolic link")

    def test_select_and_load_traversal_kb_name(self, tmp_kb_dir: Path):
        """kb_name 含路径穿越时应抛出 PathSecurityError"""
        with pytest.raises(PathSecurityError):
            select_and_load_files("测试", "../etc", knowledge_root=tmp_kb_dir)


class TestTokenize:
    """分词测试"""

    def test_english_tokens(self):
        tokens = _tokenize("How does SSE protocol work")
        assert "sse" in tokens
        assert "protocol" in tokens
        assert "how" not in tokens  # 停用词

    def test_chinese_tokens(self):
        tokens = _tokenize("知识库如何匹配")
        assert "知识库" in tokens
        assert "匹配" in tokens
        assert "如何" not in tokens  # 停用词

    def test_mixed_tokens(self):
        tokens = _tokenize("SSE 协议的事件类型")
        assert "sse" in tokens
        assert "协议" in tokens
        assert "事件" in tokens
        assert "类型" in tokens

    def test_empty_text(self):
        assert _tokenize("") == set()
        assert _tokenize(None) == set()  # type: ignore

    def test_stopwords_filtered(self):
        tokens = _tokenize("the and of 的 了 是")
        # 全是停用词
        assert len(tokens) == 0


class TestFileScanning:
    """文件扫描测试"""

    def test_iter_kb_files(self, tmp_kb_dir: Path):
        """应扫描到白名单后缀文件"""
        kb_root = create_test_file(tmp_kb_dir, "doc.md", "# Title")
        create_test_file(tmp_kb_dir, "code.py", "print('hello')")

        files = list(_iter_kb_files(kb_root))
        assert len(files) >= 2  # 至少扫描到 md 和 py

    def test_iter_kb_files_skip_binary(self, tmp_kb_dir: Path):
        """非白名单后缀应被跳过"""
        kb_root = create_test_file(tmp_kb_dir, "doc.md", "# Doc")
        create_test_file(tmp_kb_dir, "image.png", "fake png")
        # .png 不在白名单中
        files = list(_iter_kb_files(kb_root))
        names = [f.suffix for f in files]
        assert ".md" in names
        assert ".png" not in names

    def test_iter_kb_files_skip_hidden(self, tmp_kb_dir: Path):
        """隐藏目录中的文件应被跳过"""
        kb_root = create_test_file(tmp_kb_dir, ".hidden/doc.md", "hidden")
        create_test_file(tmp_kb_dir, "visible.md", "visible")

        files = list(_iter_kb_files(kb_root))
        assert len(files) >= 1
        assert all(".hidden" not in str(f) for f in files)

    def test_empty_kb(self, tmp_kb_dir: Path):
        """知识库目录存在但无文件时应返回空列表"""
        kb_root = create_test_file(tmp_kb_dir, "empty", "")
        files = list(_iter_kb_files(kb_root))
        assert len(files) == 0

    def test_build_candidates_skips_index(self, tmp_kb_dir: Path):
        """索引.md 不应出现在候选列表中"""
        kb_root = create_test_file(tmp_kb_dir, "索引.md", "# Index")
        create_test_file(tmp_kb_dir, "doc.md", "# Doc")

        candidates = _build_candidates(kb_root)
        paths = {c.rel_path for c in candidates}
        assert "doc.md" in paths
        assert "索引.md" not in paths

    def test_scoring_filename_hit(self):
        """文件名命中应加分"""
        candidates = [
            FileCandidate(rel_path="sse-protocol.md", abs_path=Path(), title="SSE Protocol", score=0),
            FileCandidate(rel_path="other.md", abs_path=Path(), title="Other", score=0),
        ]
        tokens = {"sse"}
        scored = _score_candidates(candidates, tokens, index_text="")
        # sse-protocol.md 的 "sse" 在文件名中命中得 +3
        assert scored[0].rel_path == "sse-protocol.md"
        assert scored[0].score >= 3


class TestSelectAndLoad:
    """完整文件选取流程测试"""

    def test_non_existent_kb(self, tmp_kb_dir: Path):
        """不存在的知识库应返回空列表"""
        result = select_and_load_files("test", "nonexistent", knowledge_root=tmp_kb_dir)
        assert result == []

    def test_empty_kb_returns_empty(self, tmp_kb_dir: Path):
        """知识库存在但无文件应返回空列表"""
        kb_dir = tmp_kb_dir / "empty_kb"
        kb_dir.mkdir()
        result = select_and_load_files("test", "empty_kb", knowledge_root=tmp_kb_dir)
        assert result == []

    def test_real_kb_loading(self, tmp_kb_dir: Path):
        """真实知识库应能选出并加载文件（关键词匹配）"""
        kb_dir = tmp_kb_dir / "docs"
        kb_dir.mkdir()
        (kb_dir / "overview.md").write_text(
            "# AnswerAgent 项目概述\n\n这是一个问答系统。\n"
            "它使用 SSE 协议进行流式输出。\n",
            encoding="utf-8",
        )
        (kb_dir / "sse-protocol.md").write_text(
            "# SSE 协议\n\n"
            "POST /api/chat/stream 返回 SSE 事件。\n"
            "事件包括: kb_matched, files_selected, token, done, error。\n",
            encoding="utf-8",
        )
        (kb_dir / "architecture.md").write_text(
            "# 架构\n\n后端使用 FastAPI 框架。\n",
            encoding="utf-8",
        )

        result = select_and_load_files("SSE 事件类型", "docs", knowledge_root=tmp_kb_dir)
        # 应该至少选到 sse-protocol.md
        loaded_paths = [f.rel_path for f in result]
        assert "sse-protocol.md" in loaded_paths


def create_test_file(kb_root: Path, rel_path: str, content: str) -> Path:
    """在 kb_root 内创建文件并确保 kb_root 包含一个子目录作为知识库

    返回知识库根目录（即 kb_root 下的一个子目录）
    """
    kb_dir = kb_root / "test_kb"
    kb_dir.mkdir(parents=True, exist_ok=True)
    file_path = kb_dir / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return kb_dir
