"""
SQLite 数据库连接管理与表初始化

使用 aiosqlite 进行异步数据库操作，避免阻塞 FastAPI 事件循环。
"""
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import aiosqlite

from core.config import settings

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """初始化数据库，创建用户表和对话元数据表（如不存在）"""
    db_path = settings.db_path
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL DEFAULT '新对话',
                user_id     TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS model_config (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_user_id
            ON conversations(user_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_updated_at
            ON conversations(updated_at)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS kb_workflow_tasks (
                id              TEXT PRIMARY KEY,
                status          TEXT NOT NULL DEFAULT 'pending',
                input_type      TEXT NOT NULL,
                input_value     TEXT NOT NULL,
                knowledge_name  TEXT,
                work_dir        TEXT,
                stage           TEXT DEFAULT 'init',
                stage_progress  TEXT DEFAULT '{}',
                task_list       TEXT DEFAULT '[]',
                completed_tasks TEXT DEFAULT '[]',
                result_path     TEXT,
                error           TEXT,
                log_file        TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
        """)
        await db.commit()

        # 迁移：为旧版 users 表补充 is_admin 列
        await _migrate_add_is_admin(db)

        # 创建默认管理员账号（如不存在）
        await _create_default_admin(db)


async def _migrate_add_is_admin(db: aiosqlite.Connection) -> None:
    """为已存在的 users 表添加 is_admin 列（兼容旧数据库）"""
    cursor = await db.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in await cursor.fetchall()]
    if "is_admin" not in columns:
        logger.info("迁移：为 users 表添加 is_admin 列")
        await db.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        await db.commit()


async def _create_default_admin(db: aiosqlite.Connection) -> None:
    """创建默认管理员账号（如不存在）"""
    from core.security import hash_password

    cursor = await db.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if await cursor.fetchone() is None:
        default_password = settings.admin_default_password
        admin_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        password_hash = hash_password(default_password)

        await db.execute(
            "INSERT INTO users (id, username, password_hash, is_admin, created_at) VALUES (?, ?, ?, 1, ?)",
            (admin_id, "admin", password_hash, now),
        )
        await db.commit()
        logger.info(f"默认管理员账号已创建（用户名: admin）")


@asynccontextmanager
async def get_db():
    """异步上下文管理器，获取数据库连接

    用法:
        async with get_db() as db:
            cursor = await db.execute("SELECT ...")
            rows = await cursor.fetchall()
    """
    db_path = settings.db_path
    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()