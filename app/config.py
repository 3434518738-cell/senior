"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    # This prototype is intentionally locked to IELTS Academic Writing.
    exam_type: Literal["academic"] = "academic"
    corpus_dir: Path = Field(default=Path("data/corpus_staging"))
    chroma_persist_dir: Path = Field(default=Path("data/chroma_db"))
    task1_collection_name: str = Field(default="ielts_academic_task1_samples")
    task2_collection_name: str = Field(default="ielts_academic_task2_samples")
    retrieval_top_k: int = Field(default=3, ge=1, le=20)
    embedding_dimension: int = Field(default=1024, ge=1)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return the process-wide validated settings instance."""

    return AppSettings()
