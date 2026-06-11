import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from core.config import settings
from core.database import init_db
from core import model_config
from api import conversations, knowledge_bases, chat, auth, admin


# 配置统一日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger(__name__)


# 创建 FastAPI 应用
app = FastAPI(
    title="AnswerAgent API",
    description="基于本地知识库的问答智能体 API",
    version="0.1.0",
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(conversations.router)
app.include_router(knowledge_bases.router)
app.include_router(chat.router)
app.include_router(auth.router)
app.include_router(admin.router)


@app.on_event("startup")
async def startup():
    """应用启动时初始化"""
    # 1. 从 .env 初始化模型配置默认值（同步）
    model_config.init_from_settings()
    # 2. 初始化数据库（含默认管理员创建）
    await init_db()
    # 3. 从 DB 加载模型配置覆盖默认值（如管理员已通过界面修改过）
    await model_config.load_from_db()
    # 4. 确保数据目录存在
    settings.ensure_directories()


@app.get("/api/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "message": "AnswerAgent is running"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8765,
        reload=False,
    )
