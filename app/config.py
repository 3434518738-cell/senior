"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Runtime settings for the local Ollama prototype."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    ollama_base_url: str = Field(default="http://localhost:11434")
    llm_model: str = Field(default="qwen3.5:latest")
    embedding_model: str = Field(default="bge-m3:latest")
    llm_num_gpu: int = Field(default=99, ge=0)
    embedding_num_gpu: int = Field(default=0, ge=0)
    llm_context_length: int = Field(default=2048, ge=256)
    request_timeout: float = Field(default=180.0, gt=0)
    keep_alive: str = Field(default="5m")
    llm_temperature: float = Field(default=0.0, ge=0, le=2)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return the process-wide validated settings instance."""

    return AppSettings()
