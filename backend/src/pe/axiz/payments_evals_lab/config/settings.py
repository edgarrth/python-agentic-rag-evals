from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BUILTIN_OPENAI_MODELS: tuple[str, ...] = (
    "gpt-5.4-mini",
    "gpt-4.1-mini",
    "gpt-4o-mini",
    "gpt-6-luna",
    "gpt-5.6-luna",
    "gpt-5.6-terra",
    "gpt-5.4",
    "gpt-5.6-sol",
    "gpt-6.1-sol",
    "gpt-6-astra",
)

class Settings(BaseSettings):
    """Configuración tipada de la aplicación."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Payments Agentic RAG Evals Lab"
    app_env: str = Field(default="local", pattern="^(local|test|docker)$")
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR)$")
    host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_port: int = 8080
    backend_url: str = "http://localhost:8000"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "axiz_payment_evals_chunks"
    memgraph_uri: str = "bolt://localhost:7687"
    memgraph_user: str = ""
    memgraph_password: str = ""

    embedding_provider: str = Field(default="hashing", pattern="^hashing$")
    embedding_dimensions: int = 384
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5.4-mini"
    openai_models: str = "gpt-5.4-mini,gpt-4.1-mini,gpt-4o-mini,gpt-6-luna,gpt-5.6-luna,gpt-5.6-terra,gpt-5.4,gpt-5.6-sol,gpt-6.1-sol,gpt-6-astra"
    openai_judge_model: str = "gpt-5.4-mini"
    openai_judge_models: str = "gpt-5.4-mini,gpt-4.1-mini,gpt-4o-mini,gpt-6-luna,gpt-5.6-luna,gpt-5.6-terra,gpt-5.4,gpt-5.6-sol,gpt-6.1-sol,gpt-6-astra"
    generation_provider: str = Field(default="openai", pattern="^(deterministic|openai)$")
    judge_provider: str = Field(default="openai", pattern="^(deterministic|openai)$")

    eval_default_suite: str = "full"
    eval_concurrency: int = 4
    eval_judge_enabled: bool = True
    promptfoo_enabled: bool = True
    deepeval_enabled: bool = True
    ragas_enabled: bool = True

    estimated_input_cost_per_million: float = 1.25
    estimated_output_cost_per_million: float = 10.0

    datasets_dir: Path = Path("datasets")
    baseline_path: Path = Path("datasets/evals/baseline.json")

    request_timeout_seconds: float = 45.0
    tool_timeout_seconds: float = 8.0
    max_top_k: int = 10

    @staticmethod
    def _csv_values(raw: str) -> list[str]:
        values: list[str] = []
        for item in raw.split(","):
            value = item.strip()
            if value and value not in values:
                values.append(value)
        return values

    @staticmethod
    def _merge_model_catalog(preferred: str, configured: str) -> list[str]:
        values: list[str] = []
        for value in [preferred, *BUILTIN_OPENAI_MODELS, *Settings._csv_values(configured)]:
            item = value.strip() if value else ""
            if item and item not in values:
                values.append(item)
        return values

    @property
    def openai_model_options(self) -> list[str]:
        return self._merge_model_catalog(self.openai_model, self.openai_models)

    @property
    def openai_judge_model_options(self) -> list[str]:
        return self._merge_model_catalog(self.openai_judge_model, self.openai_judge_models)


@lru_cache
def get_settings() -> Settings:
    return Settings()
