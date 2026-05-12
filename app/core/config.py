"""Application settings."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Talking BI v2"
    default_session_ttl_minutes: int = 1440
    max_result_rows: int = 5000
    storage_root: Path = Path("./storage")
    session_store_path: Path = Path("./storage/sessions")
    dataset_store_path: Path = Path("./storage/datasets")
    result_cache_path: Path = Path("./storage/result_cache")
    llm_enabled: bool = False
    llm_timeout_seconds: float = 45.0
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_heavy_model: str = "llama-3.3-70b-versatile"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_light_model: str = "nvidia/nemotron-3-nano-30b-a3b:free"
    openrouter_app_name: str = "Talking BI v2"
    openrouter_site_url: str = "http://localhost:8000"
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_light_model: str = "llama3.1:latest"
    ollama_heavy_model: str = "llama3.1:latest"
    llm_default_temperature: float = 0.1
    llm_mode: Literal["hybrid", "deterministic"] = "hybrid"


settings = Settings()
