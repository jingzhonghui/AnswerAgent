"""
SQLite 数据库连接管理与表初始化

使用 aiosqlite 进行异步数据库操作，避免阻塞 FastAPI 事件循环。
"""
from contextlib import asynccontextmanager

import aiosqlite

from core.config import settings


async def init_db() -> None:
    """初始化数据库，创建用户表和对话元数据表（如不存在）"""
    db_path = settings.db_path
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
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
            CREATE INDEX IF NOT EXISTS idx_conversations_user_id
            ON conversations(user_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_updated_at
            ON conversations(updated_at)
        """)
        await db.commit()


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