import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from core.config import settings
from core.database import init_db
from core import model_config
from api import conversations, knowledge_bases, chat, auth, admin, external_chat, public


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
app.include_router(public.router)
app.include_router(conversations.router)
app.include_router(knowledge_bases.router)
app.include_router(chat.router)
app.include_router(external_chat.router)
app.include_router(auth.router)
app.include_router(admin.router)


@app.on_event("startup")
async def startup():
    """应用启动时初始化"""
    # 1. 从 Settings 硬编码默认值初始化配置缓存（同步）
    model_config.init_from_settings()
    # 2. 初始化数据库（含默认管理员创建）
    await init_db()
    # 3. 从 DB 加载配置覆盖默认值
    await model_config.load_from_db()
    # 4. 将 DB 配置同步回 settings 对象（让 settings.xxx 调用自动获得 DB 值）
    _sync_config_to_settings()
    # 5. 确保数据目录存在
    settings.ensure_directories()


def _sync_config_to_settings() -> None:
    """将 model_config 缓存中的非 LLM 配置同步回 Settings 对象

    这样 kb_router.py、security.py、database.py 等文件中已有的
    settings.xxx 调用无需修改，自动获得数据库中的配置值。
    """
    mc = model_config
    settings.knowledge_path = mc.get("knowledge_path", settings.knowledge_path)
    settings.data_path = mc.get("data_path", settings.data_path)
    settings.history_window = mc.get_int("history_window", settings.history_window)
    settings.jwt_secret_key = mc.get("jwt_secret_key", settings.jwt_secret_key)
    settings.jwt_algorithm = mc.get("jwt_algorithm", settings.jwt_algorithm)
    settings.jwt_expire_minutes = mc.get_int("jwt_expire_minutes", settings.jwt_expire_minutes)
    settings.admin_default_password = mc.get("admin_default_password", settings.admin_default_password)
    logger.info("配置已同步到 Settings 对象")


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
