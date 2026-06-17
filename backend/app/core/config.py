"""
Configuration management for AnswerAgent backend.
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings — 默认值来源，运行时配置已迁移到数据库。

所有配置已迁移到数据库 model_config 表管理。此 Settings 类仅在
首次启动时提供硬编码默认值；运行时配置通过 core.model_config 服务
（内存缓存 + SQLite 持久化）读取。

注意：pydantic-settings 的 BaseSettings 仍会读取同名环境变量作为
默认值，但数据库中的值优先级更高（main.py 启动流程会覆盖）。
"""

    # LLM Provider（默认模型）
    llm_provider: str = "openai"  # "openai" | "anthropic"
    api_key: str = ""
    base_url: str = ""
    model: str = "gpt-4o"

    # Paths
    knowledge_path: str = "./knowledge"
    data_path: str = "./data/conversations"

    # Chat settings
    history_window: int = 10  # Number of conversation rounds to keep
    max_context_chars: int = 150  # 上下文总字符预算上限(K)，0=不限制，150=150K

    # Deep thinking (reasoning) model — 完全独立配置，可与默认模型不同 provider
    deep_model_enabled: bool = True
    deep_llm_provider: str = ""  # "openai" | "anthropic"，空则复用 llm_provider
    deep_api_key: str = ""
    deep_base_url: str = ""
    deep_model: str = "o1-mini"
    deep_temperature: float = 0.1

    # JWT 认证配置
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 默认 24 小时

    # 管理员配置
    admin_default_password: str = "admin123"  # 默认管理员初始密码，首次启动时创建

    class Config:
        # .env 文件已移除，所有配置通过数据库 model_config 表管理
        case_sensitive = False

    def get_knowledge_path(self) -> Path:
        """Get absolute path to knowledge directory."""
        backend_root = Path(__file__).parent.parent.parent
        path = Path(self.knowledge_path)
        if not path.is_absolute():
            path = backend_root / path
        return path.resolve()

    def get_data_path(self) -> Path:
        """Get absolute path to conversations data directory."""
        backend_root = Path(__file__).parent.parent.parent
        path = Path(self.data_path)
        if not path.is_absolute():
            path = backend_root / path
        return path.resolve()

    @property
    def db_path(self) -> Path:
        """Get absolute path to the SQLite database file."""
        backend_root = Path(__file__).parent.parent.parent
        db_path = backend_root / "data" / "answeragent.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return db_path

    def ensure_directories(self) -> None:
        """Ensure required directories exist."""
        self.get_data_path().mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()