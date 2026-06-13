"""公开配置接口

GET /api/public/config

无需认证，返回前端可用的公开配置项（如 deep_model_enabled 控制按钮显隐）。
"""
from __future__ import annotations

from fastapi import APIRouter

from core.model_config import get

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/config")
async def get_public_config():
    """获取公开配置项（无需认证）

    返回前端所需的非敏感配置，例如深度思考功能是否启用。
    """
    return {
        "deep_model_enabled": get("deep_model_enabled", "true").lower() == "true",
    }