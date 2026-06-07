from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from core.config import settings
from core.database import init_db
from api import conversations, knowledge_bases, chat, auth


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


@app.on_event("startup")
async def startup():
    """应用启动时初始化"""
    await init_db()
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
