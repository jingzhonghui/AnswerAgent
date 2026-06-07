"""
Configuration management for AnswerAgent backend.
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment/.env file."""

    # LLM Provider
    llm_provider: str = "openai"  # openai | anthropic

    # OpenAI Configuration
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o"

    # Anthropic Configuration
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # Paths
    knowledge_path: str = "./knowledge"
    data_path: str = "./data/conversations"

    # Chat settings
    history_window: int = 10  # Number of conversation rounds to keep

    # JWT 认证配置
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 默认 24 小时

    class Config:
        env_file = str(
            Path(__file__).parent.parent.parent / ".env"
        )  # backend/.env，相对于 config.py(->core->app->backend)
        env_file_encoding = "utf-8"
        case_sensitive = False

    def get_knowledge_path(self) -> Path:
        """Get absolute path to knowledge directory."""
        # If path is relative, resolve it relative to the backend root
        backend_root = Path(__file__).parent.parent.parent
        path = Path(self.knowledge_path)
        if not path.is_absolute():
            path = backend_root / path
        return path.resolve()

    def get_data_path(self) -> Path:
        """Get absolute path to conversations data directory."""
        # If path is relative, resolve it relative to the backend root
        # Backend root is 2 levels up from this file (core/config.py -> app -> backend)
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
