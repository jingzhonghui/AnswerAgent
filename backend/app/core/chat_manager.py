"""对话管理模块

对话元数据（ID、标题、用户归属等）存储在 SQLite 数据库中，
对话内容（消息列表）存储在独立的 JSON 文件中。

安全特性:
- 所有文件路径 resolve 后校验在 DATA_PATH 内
- 防止路径穿越攻击
- 使用原子写入（先写临时文件，再重命名）
"""
import json
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import ValidationError

from core.config import settings
from models.schemas import (
    ConversationDetail,
    ConversationSummary,
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

    对话元数据存储在 SQLite，消息内容存储在 JSON 文件。
    """

    def __init__(self, data_path: Optional[str] = None, db_path: Optional[str] = None):
        """初始化对话管理器

        Args:
            data_path: 对话 JSON 文件存储目录，默认使用 settings.get_data_path()
            db_path: SQLite 数据库文件路径，默认使用 settings.db_path
        """
        self.data_path = Path(data_path or settings.get_data_path()).resolve()
        self.data_path.mkdir(parents=True, exist_ok=True)

        self._db_path = str(db_path or settings.db_path)
        self._ensure_conversations_table()
        self.sync_from_json_files()

    # ==================== SQLite 连接 ====================

    def _ensure_conversations_table(self) -> None:
        """确保对话元数据表存在"""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id          TEXT PRIMARY KEY,
                    title       TEXT NOT NULL DEFAULT '新对话',
                    user_id     TEXT,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at)"
            )
            conn.commit()
        finally:
            conn.close()

    def _get_db(self) -> sqlite3.Connection:
        """获取同步 SQLite 连接"""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ==================== 旧数据迁移 ====================

    def sync_from_json_files(self) -> int:
        """将磁盘上无对应 DB 记录的 JSON 文件同步到数据库

        用于迁移已有的历史对话数据。

        Returns:
            int: 同步的对话数量
        """
        count = 0
        conn = self._get_db()
        try:
            for json_file in self.data_path.glob("*.json"):
                conv_id = json_file.stem
                cursor = conn.execute(
                    "SELECT 1 FROM conversations WHERE id = ?", (conv_id,)
                )
                if cursor.fetchone() is not None:
                    continue  # 已有 DB 记录，跳过

                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except (json.JSONDecodeError, KeyError):
                    continue  # 跳过损坏文件

                conn.execute(
                    "INSERT INTO conversations (id, title, user_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (
                        data.get('id', conv_id),
                        data.get('title', '新对话'),
                        data.get('user_id'),
                        data.get('created_at', datetime.now().isoformat()),
                        data.get('updated_at', datetime.now().isoformat()),
                    ),
                )
                count += 1

            if count > 0:
                conn.commit()
        finally:
            conn.close()

        return count

    # ==================== 文件路径 & 安全校验 ====================

    def _validate_conversation_id(self, conversation_id: str) -> None:
        """验证对话 ID 格式

        Args:
            conversation_id: 对话 ID

        Raises:
            ValueError: ID 格式无效
        """
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

        file_path = (self.data_path / f"{conversation_id}.json").resolve()

        if not str(file_path).startswith(str(self.data_path)):
            raise PathSecurityError(
                f"Path traversal detected: {conversation_id} resolves outside DATA_PATH"
            )

        return file_path

    # ==================== JSON 文件读写（消息内容） ====================

    def _atomic_write_json(self, file_path: Path, data: dict) -> None:
        """原子写入 JSON 文件"""
        temp_fd, temp_path = tempfile.mkstemp(
            dir=file_path.parent, prefix=f".{file_path.stem}_"
        )
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            os.replace(temp_path, file_path)
        except Exception:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise

    def _load_conversation(self, conversation_id: str) -> ConversationDetail:
        """从 JSON 文件加载对话（含完整消息内容）

        Args:
            conversation_id: 对话 ID

        Returns:
            ConversationDetail: 包含完整消息的对话数据

        Raises:
            ConversationNotFoundError: 对话不存在或文件损坏
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
            return ConversationDetail(**data)
        except ValidationError as e:
            raise ConversationNotFoundError(
                f"Conversation data corrupted (schema validation error): {conversation_id}"
            ) from e

    def _save_conversation(self, conversation: ConversationDetail) -> None:
        """将对话完整保存到 JSON 文件（含消息内容）"""
        file_path = self._get_conversation_path(conversation.id)
        data = conversation.model_dump()
        self._atomic_write_json(file_path, data)

    # ==================== 对话 CRUD ====================

    def list_conversations(self) -> List[ConversationSummary]:
        """获取所有对话列表（无用户过滤），按 updated_at 倒序

        Returns:
            List[ConversationSummary]: 对话列表
        """
        conn = self._get_db()
        try:
            cursor = conn.execute(
                "SELECT id, title, updated_at FROM conversations ORDER BY updated_at DESC"
            )
            return [
                ConversationSummary(
                    id=row['id'],
                    title=row['title'],
                    updated_at=datetime.fromisoformat(row['updated_at']),
                    message_count=None,
                )
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    def list_conversations_by_user(self, user_id: str) -> List[ConversationSummary]:
        """获取指定用户的对话列表，按 updated_at 倒序

        Args:
            user_id: 用户 ID

        Returns:
            List[ConversationSummary]: 对话列表
        """
        conn = self._get_db()
        try:
            cursor = conn.execute(
                "SELECT id, title, updated_at FROM conversations WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            )
            return [
                ConversationSummary(
                    id=row['id'],
                    title=row['title'],
                    updated_at=datetime.fromisoformat(row['updated_at']),
                    message_count=None,
                )
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    def create_conversation(self, title: str = "新对话", user_id: Optional[str] = None) -> str:
        """创建新对话

        先在 SQLite 插入元数据，再创建空的 JSON 消息文件。
        如果 DB 插入失败，不会创建 JSON 文件（原子性保证）。

        Args:
            title: 对话标题
            user_id: 所属用户 ID

        Returns:
            str: 新创建对话的 ID
        """
        conversation_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        conn = self._get_db()
        try:
            conn.execute(
                "INSERT INTO conversations (id, title, user_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (conversation_id, title, user_id, now, now),
            )
            conn.commit()
        except Exception:
            conn.close()
            raise
        conn.close()

        # 创建空的 JSON 消息文件
        conversation = ConversationDetail(
            id=conversation_id,
            title=title,
            created_at=datetime.fromisoformat(now),
            updated_at=datetime.fromisoformat(now),
            messages=[],
            user_id=user_id,
        )
        self._save_conversation(conversation)

        return conversation_id

    def get_conversation(self, conversation_id: str) -> ConversationDetail:
        """获取对话详情（含完整消息内容）

        元数据（标题、时间）从 SQLite 获取，消息内容从 JSON 文件加载。
        SQLite 是元数据的权威来源。

        Args:
            conversation_id: 对话 ID

        Returns:
            ConversationDetail: 对话详情

        Raises:
            ConversationNotFoundError: 对话不存在
        """
        self._get_conversation_path(conversation_id)  # 只做格式校验

        # 从 DB 获取元数据
        conn = self._get_db()
        try:
            cursor = conn.execute(
                "SELECT id, title, user_id, created_at, updated_at FROM conversations WHERE id = ?",
                (conversation_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise ConversationNotFoundError(
                    f"Conversation not found: {conversation_id}"
                )
            db_meta = {
                "title": row["title"],
                "user_id": row["user_id"],
                "created_at": datetime.fromisoformat(row["created_at"]),
                "updated_at": datetime.fromisoformat(row["updated_at"]),
            }
        finally:
            conn.close()

        # 从 JSON 加载消息内容
        conv = self._load_conversation(conversation_id)

        # 以 DB 元数据覆盖 JSON 中的值（DB 是元数据权威来源）
        conv.title = db_meta["title"]
        conv.user_id = db_meta["user_id"]
        conv.created_at = db_meta["created_at"]
        conv.updated_at = db_meta["updated_at"]

        return conv

    def delete_conversation(self, conversation_id: str) -> None:
        """删除对话

        同步删除 DB 记录和 JSON 文件。

        Args:
            conversation_id: 对话 ID

        Raises:
            ConversationNotFoundError: 对话不存在
        """
        file_path = self._get_conversation_path(conversation_id)

        # 删除 DB 记录
        conn = self._get_db()
        try:
            cursor = conn.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,)
            )
            if cursor.rowcount == 0:
                raise ConversationNotFoundError(
                    f"Conversation not found: {conversation_id}"
                )
            conn.commit()
        finally:
            conn.close()

        # 删除 JSON 文件（如果存在）
        if file_path.exists():
            file_path.unlink()

    def rename_conversation(self, conversation_id: str, title: str) -> None:
        """重命名对话（仅更新 DB，不碰 JSON 文件）

        Args:
            conversation_id: 对话 ID
            title: 新标题

        Raises:
            ConversationNotFoundError: 对话不存在
        """
        self._get_conversation_path(conversation_id)  # 只做格式校验

        conn = self._get_db()
        try:
            cursor = conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, datetime.now().isoformat(), conversation_id),
            )
            if cursor.rowcount == 0:
                raise ConversationNotFoundError(
                    f"Conversation not found: {conversation_id}"
                )
            conn.commit()
        finally:
            conn.close()

    # ==================== 消息操作 ====================

    def append_user_message(self, conversation_id: str, content: str) -> None:
        """追加用户消息（仅操作 JSON 文件）

        自动去重：如果最后一条消息也是相同内容的用户消息，且时间差 < 10 秒，
        跳过保存（防止前端重复发送）。

        Args:
            conversation_id: 对话 ID
            content: 消息内容

        Raises:
            ConversationNotFoundError: 对话不存在
        """
        conversation = self._load_conversation(conversation_id)

        # 去重检查：防止短时间内重复写入相同用户消息
        if conversation.messages:
            last_msg = conversation.messages[-1]
            if last_msg.role == "user" and last_msg.content == content:
                if last_msg.created_at:
                    delta = (datetime.now() - last_msg.created_at).total_seconds()
                    if delta < 10:
                        return  # 重复消息，跳过

        message = Message(
            id=str(uuid.uuid4()),
            role="user",
            content=content,
            created_at=datetime.now(),
        )

        conversation.messages.append(message)
        conversation.updated_at = datetime.now()
        self._save_conversation(conversation)

        # 同步更新 DB 中的 updated_at
        self._update_timestamp(conversation_id)

    def append_assistant_message(
        self,
        conversation_id: str,
        content: str,
        kb_names: Optional[List[str]] = None,
        files_used: Optional[List[str]] = None,
        thinking_steps: Optional[List[dict]] = None,
    ) -> None:
        """追加助手消息

        如果 kb_names 有更新，也同步更新对话的关联知识库。

        Args:
            conversation_id: 对话 ID
            content: 消息内容
            kb_names: 关联的知识库列表
            files_used: 引用的文件列表
            thinking_steps: 深度思考步骤列表（仅 deep 模式）

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
                parts = file_path.split('/', 1)
                kb_name = parts[0] if len(parts) > 1 else ""
                rel_path = parts[1] if len(parts) > 1 else file_path
                files_used_objects.append(FileSelection(
                    kb_name=kb_name,
                    file_path=rel_path,
                    file_name=Path(rel_path).name,
                ))

        # 构建 thinking_steps 对象列表
        thinking_steps_objects = None
        if thinking_steps:
            from models.schemas import ThinkingStep
            thinking_steps_objects = [
                ThinkingStep(**step) for step in thinking_steps
            ]

        message = Message(
            id=str(uuid.uuid4()),
            role="assistant",
            content=content,
            created_at=datetime.now(),
            kb_names=kb_names,
            files_used=files_used_objects,
            thinking_steps=thinking_steps_objects,
        )

        conversation.messages.append(message)
        conversation.updated_at = datetime.now()
        self._save_conversation(conversation)

        # 同步更新 DB 中的 updated_at
        self._update_timestamp(conversation_id)

    def get_recent_history(self, conversation_id: str, window: int = 10) -> List[dict]:
        """获取最近 N 轮对话历史（仅从 JSON 读取）

        Args:
            conversation_id: 对话 ID
            window: 保留轮数（每轮 = 1问1答），默认 10

        Returns:
            List[dict]: 消息列表，每项包含 role 和 content

        Raises:
            ConversationNotFoundError: 对话不存在
        """
        conversation = self._load_conversation(conversation_id)

        messages = conversation.messages[-window * 2:] if conversation.messages else []

        return [
            {
                "role": msg.role,
                "content": msg.content,
            }
            for msg in messages
        ]

    # ==================== 内部辅助 ====================

    def _update_timestamp(self, conversation_id: str) -> None:
        """同步更新 DB 中的 updated_at 时间戳"""
        conn = self._get_db()
        try:
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), conversation_id),
            )
            conn.commit()
        finally:
            conn.close()


# 全局对话管理器实例
chat_manager = ChatManager()
