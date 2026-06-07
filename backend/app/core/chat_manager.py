"""对话 JSON 持久化管理模块

提供对话的创建、列表、详情、重命名、删除等操作，
每个对话保存为独立的 JSON 文件。

安全特性:
- 所有文件路径 resolve 后校验在 DATA_PATH 内
- 防止路径穿越攻击
- 使用原子写入（先写临时文件，再重命名）
"""
import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import ValidationError

from core.config import settings
from models.schemas import (
    ConversationInStorage,
    ConversationSummary,
    ConversationDetail,
    Message,
)


class PathSecurityError(Exception):
    """路径安全异常"""
    pass


class ConversationNotFoundError(Exception):
    """对话不存在异常"""
    pass


class ChatManager:
    """对话管理器

    负责对话的 CRUD 操作和 JSON 文件持久化。
    """

    def __init__(self, data_path: Optional[str] = None):
        """初始化对话管理器

        Args:
            data_path: 对话数据存储目录，默认使用 settings.DATA_PATH
        """
        self.data_path = Path(data_path or settings.get_data_path()).resolve()
        # 确保数据目录存在
        self.data_path.mkdir(parents=True, exist_ok=True)

    def _validate_conversation_id(self, conversation_id: str) -> None:
        """验证对话 ID 格式

        Args:
            conversation_id: 对话 ID

        Raises:
            ValueError: ID 格式无效
        """
        # 只允许 UUID 格式的 ID：550e8400-e29b-41d4-a716-446655440000
        try:
            uuid.UUID(conversation_id)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid conversation_id format: {conversation_id}")

    def _get_conversation_path(self, conversation_id: str) -> Path:
        """获取对话文件路径，并验证路径安全

        Args:
            conversation_id: 对话 ID

        Returns:
            Path: 对话文件的绝对路径

        Raises:
            PathSecurityError: 路径不在允许的 DATA_PATH 目录内
        """
        self._validate_conversation_id(conversation_id)

        # 构建文件路径
        file_path = (self.data_path / f"{conversation_id}.json").resolve()

        # 安全检查：确保解析后的路径在 DATA_PATH 内
        # 防止路径穿越攻击（如 conversation_id = "../../../etc/passwd"）
        if not str(file_path).startswith(str(self.data_path)):
            raise PathSecurityError(
                f"Path traversal detected: {conversation_id} resolves outside DATA_PATH"
            )

        return file_path

    def _atomic_write_json(self, file_path: Path, data: dict) -> None:
        """原子写入 JSON 文件

        先写入临时文件，再重命名，避免写入过程中断导致文件损坏。

        Args:
            file_path: 目标文件路径
            data: 要写入的数据
        """
        # 在同一目录创建临时文件，确保原子重命名有效
        temp_fd, temp_path = tempfile.mkstemp(
            dir=file_path.parent,
            prefix=f".{file_path.stem}_"
        )
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            # 原子重命名
            os.replace(temp_path, file_path)
        except Exception:
            # 清理临时文件
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise

    def _load_conversation(self, conversation_id: str) -> ConversationInStorage:
        """加载对话数据

        Args:
            conversation_id: 对话 ID

        Returns:
            ConversationInStorage: 对话数据

        Raises:
            ConversationNotFoundError: 对话不存在
        """
        file_path = self._get_conversation_path(conversation_id)

        if not file_path.exists():
            raise ConversationNotFoundError(f"Conversation not found: {conversation_id}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ConversationNotFoundError(
                f"Conversation data corrupted (JSON parse error): {conversation_id}"
            ) from e

        # 解析 datetime 字段
        for key in ['created_at', 'updated_at']:
            if data.get(key):
                data[key] = datetime.fromisoformat(data[key])

        for msg in data.get('messages', []):
            if msg.get('created_at'):
                msg['created_at'] = datetime.fromisoformat(msg['created_at'])

        try:
            return ConversationInStorage(**data)
        except ValidationError as e:
            raise ConversationNotFoundError(
                f"Conversation data corrupted (schema validation error): {conversation_id}"
            ) from e

    def _save_conversation(self, conversation: ConversationInStorage) -> None:
        """保存对话数据

        Args:
            conversation: 对话数据
        """
        file_path = self._get_conversation_path(conversation.id)
        data = conversation.model_dump()
        self._atomic_write_json(file_path, data)

    def list_conversations(self) -> List[ConversationSummary]:
        """获取对话列表，按 updated_at 倒序排列

        Returns:
            List[ConversationSummary]: 对话列表
        """
        conversations = []

        # 遍历所有 JSON 文件
        for json_file in self.data_path.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 解析日期
                updated_at = data.get('updated_at', '')
                if updated_at:
                    updated_at = datetime.fromisoformat(updated_at)

                conversations.append(ConversationSummary(
                    id=data['id'],
                    title=data.get('title', '未命名对话'),
                    kb_names=data.get('kb_names', []),
                    updated_at=updated_at or datetime.now(),
                    message_count=len(data.get('messages', [])),
                ))
            except (json.JSONDecodeError, KeyError, ValueError):
                # 跳过损坏的文件
                continue

        # 按 updated_at 倒序排列
        conversations.sort(key=lambda x: x.updated_at, reverse=True)
        return conversations

    def list_conversations_by_user(self, user_id: str) -> List[ConversationSummary]:
        """获取指定用户的对话列表，按 updated_at 倒序排列

        只返回 user_id 与当前用户匹配的对话（严格多用户隔离）。

        Args:
            user_id: 用户 ID

        Returns:
            List[ConversationSummary]: 对话列表
        """
        conversations = []

        for json_file in self.data_path.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 严格过滤：只返回 user_id 完全匹配的对话
                conv_user_id = data.get('user_id')
                if conv_user_id != user_id:
                    continue

                updated_at = data.get('updated_at', '')
                if updated_at:
                    updated_at = datetime.fromisoformat(updated_at)

                conversations.append(ConversationSummary(
                    id=data['id'],
                    title=data.get('title', '未命名对话'),
                    kb_names=data.get('kb_names', []),
                    updated_at=updated_at or datetime.now(),
                    message_count=len(data.get('messages', [])),
                ))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue

        conversations.sort(key=lambda x: x.updated_at, reverse=True)
        return conversations

    def create_conversation(self, title: str = "新对话", user_id: Optional[str] = None) -> str:
        """创建新对话

        Args:
            title: 对话标题
            user_id: 所属用户 ID（可选，用于多用户隔离）

        Returns:
            str: 新创建对话的 ID
        """
        conversation_id = str(uuid.uuid4())
        now = datetime.now()

        conversation = ConversationInStorage(
            id=conversation_id,
            title=title,
            kb_names=[],
            created_at=now,
            updated_at=now,
            messages=[],
            user_id=user_id,
        )

        self._save_conversation(conversation)
        return conversation_id

    def get_conversation(self, conversation_id: str) -> ConversationDetail:
        """获取对话详情

        Args:
            conversation_id: 对话 ID

        Returns:
            ConversationDetail: 对话详情

        Raises:
            ConversationNotFoundError: 对话不存在
        """
        conv = self._load_conversation(conversation_id)

        return ConversationDetail(
            id=conv.id,
            title=conv.title,
            kb_names=conv.kb_names,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            messages=conv.messages,
            user_id=conv.user_id,
        )

    def delete_conversation(self, conversation_id: str) -> None:
        """删除对话

        Args:
            conversation_id: 对话 ID

        Raises:
            ConversationNotFoundError: 对话不存在
        """
        file_path = self._get_conversation_path(conversation_id)

        if not file_path.exists():
            raise ConversationNotFoundError(f"Conversation not found: {conversation_id}")

        file_path.unlink()

    def rename_conversation(self, conversation_id: str, title: str) -> None:
        """重命名对话

        Args:
            conversation_id: 对话 ID
            title: 新标题

        Raises:
            ConversationNotFoundError: 对话不存在
        """
        conversation = self._load_conversation(conversation_id)
        conversation.title = title
        conversation.updated_at = datetime.now()
        self._save_conversation(conversation)

    def append_user_message(self, conversation_id: str, content: str) -> None:
        """追加用户消息

        Args:
            conversation_id: 对话 ID
            content: 消息内容

        Raises:
            ConversationNotFoundError: 对话不存在
        """
        conversation = self._load_conversation(conversation_id)

        message = Message(
            id=str(uuid.uuid4()),
            role="user",
            content=content,
            created_at=datetime.now(),
        )

        conversation.messages.append(message)
        conversation.updated_at = datetime.now()
        self._save_conversation(conversation)

    def append_assistant_message(
        self,
        conversation_id: str,
        content: str,
        kb_names: Optional[List[str]] = None,
        files_used: Optional[List[str]] = None,
    ) -> None:
        """追加助手消息

        Args:
            conversation_id: 对话 ID
            content: 消息内容
            kb_names: 关联的知识库列表
            files_used: 引用的文件列表

        Raises:
            ConversationNotFoundError: 对话不存在
        """
        conversation = self._load_conversation(conversation_id)

        # 更新对话关联的知识库（去重合并）
        if kb_names:
            existing_kb = set(conversation.kb_names)
            existing_kb.update(kb_names)
            conversation.kb_names = list(existing_kb)

        # 构建 files_used 对象列表
        files_used_objects = None
        if files_used:
            from models.schemas import FileSelection
            files_used_objects = []
            for file_path in files_used:
                # 尝试解析知识库名称和文件路径
                parts = file_path.split('/', 1)
                kb_name = parts[0] if len(parts) > 1 else ""
                rel_path = parts[1] if len(parts) > 1 else file_path
                files_used_objects.append(FileSelection(
                    kb_name=kb_name,
                    file_path=rel_path,
                    file_name=Path(rel_path).name,
                ))

        message = Message(
            id=str(uuid.uuid4()),
            role="assistant",
            content=content,
            created_at=datetime.now(),
            kb_names=kb_names,
            files_used=files_used_objects,
        )

        conversation.messages.append(message)
        conversation.updated_at = datetime.now()
        self._save_conversation(conversation)

    def get_recent_history(self, conversation_id: str, window: int = 10) -> List[dict]:
        """获取最近 N 轮对话历史

        Args:
            conversation_id: 对话 ID
            window: 保留轮数（每轮 = 1问1答），默认 10

        Returns:
            List[dict]: 消息列表，每项包含 role 和 content

        Raises:
            ConversationNotFoundError: 对话不存在
        """
        conversation = self._load_conversation(conversation_id)

        # 取最后 window*2 条消息（问答成对）
        messages = conversation.messages[-window * 2:] if conversation.messages else []

        return [
            {
                "role": msg.role,
                "content": msg.content,
            }
            for msg in messages
        ]


# 全局对话管理器实例
chat_manager = ChatManager()
