"""
SQLite 数据库连接管理与用户表初始化

使用 aiosqlite 进行异步数据库操作，避免阻塞 FastAPI 事件循环。
"""
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from core.config import settings


# 数据库文件路径：backend/data/answeragent.db
def _get_db_path() -> Path:
    backend_root = Path(__file__).parent.parent.parent
    db_path = backend_root / "data" / "answeragent.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


async def init_db() -> None:
    """初始化数据库，创建用户表（如不存在）"""
    db_path = _get_db_path()
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
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
    db_path = _get_db_path()
    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()