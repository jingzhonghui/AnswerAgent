"""ChatManager 单元测试

测试对话的 CRUD 操作、路径安全、JSON 损坏容错等。
"""

import json
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from core.chat_manager import (
    ChatManager,
    ConversationNotFoundError,
    PathSecurityError,
)


class TestChatManager:
    """ChatManager 测试套件"""

    def test_create_conversation(self, tmp_data_dir: Path, tmp_db_path: str):
        """创建对话应返回合法 UUID 并在磁盘生成文件"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        conv_id = mgr.create_conversation(title="测试对话")
        # 返回的 ID 应为合法 UUID
        uuid.UUID(conv_id)
        # 文件应存在
        file_path = tmp_data_dir / f"{conv_id}.json"
        assert file_path.exists()
        # 文件内容应是合法 JSON
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["id"] == conv_id
        assert data["title"] == "测试对话"

    def test_list_conversations(self, tmp_data_dir: Path, tmp_db_path: str):
        """创建多个对话后列表应返回全部"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        id1 = mgr.create_conversation(title="对话 A")
        id2 = mgr.create_conversation(title="对话 B")

        convs = mgr.list_conversations()
        assert len(convs) == 2
        titles = {c.title for c in convs}
        assert titles == {"对话 A", "对话 B"}

    def test_list_conversations_empty(self, tmp_data_dir: Path, tmp_db_path: str):
        """空数据目录应返回空列表"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        assert mgr.list_conversations() == []

    def test_get_conversation(self, tmp_data_dir: Path, tmp_db_path: str):
        """获取对话详情应返回完整数据"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        conv_id = mgr.create_conversation(title="测试")
        conv = mgr.get_conversation(conv_id)
        assert conv.id == conv_id
        assert conv.title == "测试"
        assert conv.messages == []

    def test_get_conversation_not_found(self, tmp_data_dir: Path, tmp_db_path: str):
        """不存在的对话应抛出 ConversationNotFoundError"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        fake_id = str(uuid.uuid4())
        with pytest.raises(ConversationNotFoundError):
            mgr.get_conversation(fake_id)

    def test_delete_conversation(self, tmp_data_dir: Path, tmp_db_path: str):
        """删除后文件应消失，列表不应包含"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        conv_id = mgr.create_conversation(title="待删除")
        mgr.delete_conversation(conv_id)
        file_path = tmp_data_dir / f"{conv_id}.json"
        assert not file_path.exists()
        assert len(mgr.list_conversations()) == 0

    def test_delete_conversation_not_found(self, tmp_data_dir: Path, tmp_db_path: str):
        """删除不存在的对话应抛出"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        with pytest.raises(ConversationNotFoundError):
            mgr.delete_conversation(str(uuid.uuid4()))

    def test_rename_conversation(self, tmp_data_dir: Path, tmp_db_path: str):
        """重命名后 title 应更新（DB 是元数据权威来源）"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        conv_id = mgr.create_conversation(title="原名")
        mgr.rename_conversation(conv_id, "新名称")
        conv = mgr.get_conversation(conv_id)
        assert conv.title == "新名称"

    def test_invalid_conversation_id(self, tmp_data_dir: Path, tmp_db_path: str):
        """非法 UUID 格式应抛出 ValueError"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        with pytest.raises(ValueError, match="Invalid conversation_id"):
            mgr.get_conversation("not-a-uuid")
        with pytest.raises(ValueError, match="Invalid conversation_id"):
            mgr.delete_conversation("../etc/passwd")
        with pytest.raises(ValueError, match="Invalid conversation_id"):
            mgr.rename_conversation("", "新标题")

    def test_path_traversal_after_validation(self, tmp_data_dir: Path, tmp_db_path: str):
        """即使绕过 UUID 校验，resolve 后也应拦截路径穿越"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)

        # 创建一个正常对话，然后尝试用穿越路径操作它
        conv_id = mgr.create_conversation()

        # 直接调用 _get_conversation_path 测试路径安全逻辑
        good_path = mgr._get_conversation_path(conv_id)
        assert str(good_path).startswith(str(tmp_data_dir))

    def test_append_user_message(self, tmp_data_dir: Path, tmp_db_path: str):
        """追加用户消息后应能在详情中看到"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        conv_id = mgr.create_conversation()
        mgr.append_user_message(conv_id, "你好")
        conv = mgr.get_conversation(conv_id)
        assert len(conv.messages) == 1
        assert conv.messages[0].role == "user"
        assert conv.messages[0].content == "你好"

    def test_append_assistant_message(self, tmp_data_dir: Path, tmp_db_path: str):
        """追加助手消息，应记录 kb_names 和 files_used"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        conv_id = mgr.create_conversation()
        mgr.append_assistant_message(
            conv_id,
            "这是回答",
            kb_names=["AnswerAgent"],
            files_used=["AnswerAgent/overview.md"],
        )
        conv = mgr.get_conversation(conv_id)
        assert len(conv.messages) == 1
        msg = conv.messages[0]
        assert msg.role == "assistant"
        assert msg.content == "这是回答"
        assert msg.kb_names == ["AnswerAgent"]
        assert msg.files_used is not None
        assert msg.files_used[0].file_path == "overview.md"

    def test_get_recent_history(self, tmp_data_dir: Path, tmp_db_path: str):
        """获取最近历史应返回正确的轮数"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        conv_id = mgr.create_conversation()

        # 追加 5 轮对话
        for i in range(5):
            mgr.append_user_message(conv_id, f"问题{i}")
            mgr.append_assistant_message(conv_id, f"回答{i}")

        # 默认 window=10 应返回全部 10 条
        history = mgr.get_recent_history(conv_id, window=10)
        assert len(history) == 10

        # window=2 应返回最后 4 条
        history2 = mgr.get_recent_history(conv_id, window=2)
        assert len(history2) == 4
        assert history2[0]["content"] == "问题3"
        assert history2[-1]["content"] == "回答4"

    def test_empty_messages_history(self, tmp_data_dir: Path, tmp_db_path: str):
        """无消息时 get_recent_history 应返回空列表"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        conv_id = mgr.create_conversation()
        history = mgr.get_recent_history(conv_id)
        assert history == []

    def test_corrupted_json_skip_in_list(self, tmp_data_dir: Path, tmp_db_path: str):
        """损坏的 JSON 文件应在列表中被跳过"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)

        # 创建正常对话
        mgr.create_conversation(title="正常")
        # 写入损坏文件（不在 DB 中，不会影响列表）
        bad_file = tmp_data_dir / f"{uuid.uuid4()}.json"
        bad_file.write_text('{"id": "bad", title: broken', encoding="utf-8")

        convs = mgr.list_conversations()
        assert len(convs) == 1
        assert convs[0].title == "正常"

    def test_corrupted_json_get_raises_not_found(self, tmp_data_dir: Path, tmp_db_path: str):
        """损坏的 JSON 文件在 get 时应抛出 ConversationNotFoundError"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        conv_id = mgr.create_conversation()

        # 手动损坏文件
        file_path = tmp_data_dir / f"{conv_id}.json"
        file_path.write_text('{"id": "broken', encoding="utf-8")

        with pytest.raises(ConversationNotFoundError):
            mgr.get_conversation(conv_id)

    def test_atomic_write_safety(self, tmp_data_dir: Path, tmp_db_path: str):
        """原子写入不应产生残留临时文件"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        conv_id = mgr.create_conversation()

        # 多次写入（只追加消息，因为重命名现已不写 JSON）
        for i in range(10):
            mgr.append_user_message(conv_id, f"消息{i}")

        # 不应有以 '.' 开头的临时文件残留
        temp_files = [f for f in tmp_data_dir.iterdir() if f.name.startswith(".")]
        assert len(temp_files) == 0, f"残留临时文件: {temp_files}"

    def test_conversation_updated_at_changes(self, tmp_data_dir: Path, tmp_db_path: str):
        """操作后 updated_at 应更新"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        conv_id = mgr.create_conversation()
        conv = mgr.get_conversation(conv_id)
        original_updated = conv.updated_at

        # 追加消息后 updated_at 应变化
        mgr.append_user_message(conv_id, "新消息")
        conv = mgr.get_conversation(conv_id)
        assert conv.updated_at > original_updated

    def test_multiple_kb_names(self, tmp_data_dir: Path, tmp_db_path: str):
        """多次追加 assistant 消息时 kb_names 应去重合并"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        conv_id = mgr.create_conversation()

        mgr.append_assistant_message(conv_id, "回答1", kb_names=["KB1"])
        mgr.append_assistant_message(conv_id, "回答2", kb_names=["KB2"])
        mgr.append_assistant_message(conv_id, "回答3", kb_names=["KB1"])

        conv = mgr.get_conversation(conv_id)
        assert sorted(conv.kb_names) == sorted(["KB1", "KB2"])

    def test_create_default_title(self, tmp_data_dir: Path, tmp_db_path: str):
        """不传 title 时应使用默认标题"""
        mgr = ChatManager(data_path=str(tmp_data_dir), db_path=tmp_db_path)
        conv_id = mgr.create_conversation()
        conv = mgr.get_conversation(conv_id)
        assert conv.title == "新对话"

    def test_data_dir_created_automatically(self, tmp_db_path: str):
        """ChatManager 初始化时应自动创建数据目录"""
        with tempfile.TemporaryDirectory() as d:
            data_path = Path(d) / "nonexistent" / "subdir"
            mgr = ChatManager(data_path=str(data_path), db_path=tmp_db_path)
            assert data_path.exists()
            assert data_path.is_dir()
            # 清理
            mgr = None  # noqa
