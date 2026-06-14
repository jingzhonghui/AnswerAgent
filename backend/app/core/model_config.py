"""
运行时配置服务——支持通过管理界面热更新 LLM 和系统配置

配置优先级: 数据库 > 硬编码默认值
- 启动时从 Settings 硬编码默认值初始化内存缓存
- 管理界面修改后同步写入 DB + 更新内存
- 对话链/LLM 工厂读取内存中的值（同步，无 DB 开销）
- 敏感配置（JWT 密钥等）不出现在管理 API 中

design:
- 单例模式，模块级 dict 存储当前配置
- `init_from_settings()` 在启动时从 Settings 默认值初始化
- `load_from_db()` 在 DB 就绪后用 DB 值覆盖
- `get()` / `get_all()` / `get_all_public()` 同步读取
- `update()` / `update_batch()` 异步写入 DB + 更新内存
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import aiosqlite
from datetime import datetime, timezone

from core.config import settings

logger = logging.getLogger(__name__)

# 配置键定义及描述
MODEL_CONFIG_KEYS = {
    # === LLM 配置（热更新） ===
    "llm_provider": "默认模型提供商（openai / anthropic）",
    "api_key": "默认模型 API Key",
    "base_url": "默认模型 API Base URL（OpenAI 兼容）",
    "model": "默认模型名称",
    "temperature": "默认模型温度（0.0 ~ 2.0）",
    "deep_model_enabled": "是否启用深度思考模式（true / false）",
    "deep_llm_provider": "深度思考模型提供商（空则复用默认）",
    "deep_api_key": "深度思考模型 API Key（空则复用默认）",
    "deep_base_url": "深度思考模型 Base URL（空则复用默认）",
    "deep_model": "深度思考模型名称",
    "deep_temperature": "深度思考模型温度（0.0 ~ 2.0）",

    # === 聊天设置（热更新） ===
    "history_window": "对话历史保留轮数（每轮 = 1问1答），默认 10",

    # === 路径配置（需重启生效） ===
    "knowledge_path": "知识库根目录路径（⚠️ 需重启生效），默认 ./knowledge",
    "data_path": "对话数据存储路径（⚠️ 需重启生效），默认 ./data/conversations",

    # === JWT 安全配置（需重启生效，敏感信息） ===
    "jwt_secret_key": "JWT 签名密钥（⚠️ 敏感信息，需重启生效）",
    "jwt_algorithm": "JWT 签名算法，默认 HS256",
    "jwt_expire_minutes": "JWT 令牌过期时间（分钟），默认 1440（24小时）",

    # === 管理员配置（仅首次启动使用） ===
    "admin_default_password": "默认管理员初始密码（仅首次启动时使用）",
}

# 敏感配置键 —— 不出现在管理 API 中
_SENSITIVE_KEYS: set[str] = {
    "jwt_secret_key",
    "admin_default_password",
}

# 需要重启才能生效的配置键
_RESTART_REQUIRED_KEYS: set[str] = {
    "knowledge_path",
    "data_path",
    "jwt_secret_key",
    "jwt_algorithm",
    "jwt_expire_minutes",
}

# 内存中的配置缓存（模块级单例）
_config_cache: Dict[str, str] = {}


def init_from_settings() -> None:
    """从 Settings 硬编码默认值初始化配置缓存（启动时调用，同步）"""
    global _config_cache
    _config_cache = {
        # LLM 配置
        "llm_provider": settings.llm_provider or "openai",
        "api_key": settings.api_key or "",
        "base_url": settings.base_url or "",
        "model": settings.model or "gpt-4o",
        "temperature": "0.6",
        "deep_model_enabled": "true" if settings.deep_model_enabled else "false",
        "deep_llm_provider": settings.deep_llm_provider or "",
        "deep_api_key": settings.deep_api_key or "",
        "deep_base_url": settings.deep_base_url or "",
        "deep_model": settings.deep_model or "o1-mini",
        "deep_temperature": str(settings.deep_temperature),
        # 聊天设置
        "history_window": str(settings.history_window),
        # 路径配置
        "knowledge_path": settings.knowledge_path or "./knowledge",
        "data_path": settings.data_path or "./data/conversations",
        # JWT 安全配置
        "jwt_secret_key": settings.jwt_secret_key or "change-me-in-production",
        "jwt_algorithm": settings.jwt_algorithm or "HS256",
        "jwt_expire_minutes": str(settings.jwt_expire_minutes),
        # 管理员配置
        "admin_default_password": settings.admin_default_password or "admin123",
    }
    logger.info("配置已从默认值初始化（%d 项）", len(_config_cache))


async def load_from_db() -> None:
    """从 SQLite 加载配置，覆盖默认值（启动时调用，异步）"""
    global _config_cache
    db_path = settings.db_path
    try:
        async with aiosqlite.connect(str(db_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT key, value FROM model_config")
            rows = await cursor.fetchall()
            for row in rows:
                if row["key"] in MODEL_CONFIG_KEYS:
                    _config_cache[row["key"]] = row["value"]
        if rows:
            logger.info(f"已从数据库加载 {len(rows)} 条模型配置")
    except Exception as e:
        logger.warning(f"从数据库加载模型配置失败，使用硬编码默认值: {e}")


def get(key: str, default: str = "") -> str:
    """获取单个配置值（同步读取内存缓存）"""
    return _config_cache.get(key, default)


def get_int(key: str, default: int = 0) -> int:
    """获取整数类型的配置值（同步读取内存缓存）"""
    try:
        return int(_config_cache.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def get_all() -> list[dict]:
    """获取全部配置项（含描述，包含敏感键）"""
    return [
        {
            "key": key,
            "value": _config_cache.get(key, ""),
            "description": desc,
        }
        for key, desc in MODEL_CONFIG_KEYS.items()
    ]


def get_all_public() -> list[dict]:
    """获取全部非敏感配置项（供管理后台 API 使用）

    敏感键（jwt_secret_key, admin_default_password）不出现在返回结果中。
    每个配置项附带 sensitive 和 restart_required 标记。
    """
    return [
        {
            "key": key,
            "value": _config_cache.get(key, ""),
            "description": desc,
            "sensitive": key in _SENSITIVE_KEYS,
            "restart_required": key in _RESTART_REQUIRED_KEYS,
        }
        for key, desc in MODEL_CONFIG_KEYS.items()
        if key not in _SENSITIVE_KEYS
    ]


async def update(key: str, value: str) -> None:
    """更新单个配置项（异步：写 DB + 更新内存）"""
    global _config_cache
    if key not in MODEL_CONFIG_KEYS:
        raise ValueError(f"未知的配置键: {key}")

    db_path = settings.db_path
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute(
            "INSERT OR REPLACE INTO model_config (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now),
        )
        await db.commit()

    _config_cache[key] = value
    logger.info(f"模型配置已更新: {key} = {value[:20]}..." if len(value) > 20 else f"模型配置已更新: {key} = {value}")


async def update_batch(configs: Dict[str, str]) -> None:
    """批量更新配置项"""
    for key, value in configs.items():
        await update(key, value)