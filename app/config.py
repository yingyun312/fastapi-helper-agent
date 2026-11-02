from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    app_mode: Literal["demo", "live"] = "demo"
    index_dir: Path = ROOT / "data/index-demo"
    deepseek_api_key: SecretStr = SecretStr("")
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-flash"
    llm_disable_thinking: bool = True
    embedding_api_key: SecretStr = SecretStr("")
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    github_token: SecretStr = SecretStr("")
    top_k: int = Field(default=5, ge=1, le=10)
    max_steps: int = Field(default=5, ge=1, le=10)
    request_timeout: float = Field(default=90, gt=0, le=300)
    tool_timeout: float = Field(default=20, gt=0, le=120)
    llm_timeout: float = Field(default=30, gt=0, le=120)
    min_bm25_score: float = Field(default=2.0, ge=0)
    min_vector_similarity: float = Field(default=0.45, ge=-1, le=1)
    demo_min_query_coverage: float = Field(default=0.5, ge=0, le=1)
    history_turns: int = Field(default=6, ge=1, le=20)
    max_sessions: int = Field(default=256, ge=1)
    session_ttl: float = Field(default=3600, gt=0)
    cache_capacity: int = Field(default=128, ge=0)
    cache_ttl: float = Field(default=300, gt=0)

    @classmethod
    def from_env(cls, *, read_dotenv: bool = True):
        import os

        values = dict(dotenv_values(ROOT / ".env")) if read_dotenv else {}
        values.update(os.environ)
        data = {key.lower(): value for key, value in values.items() if value is not None}
        if "index_dir" not in data:
            data["index_dir"] = ROOT / (
                "data/index-live" if data.get("app_mode") == "live" else "data/index-demo"
            )
        result = cls.model_validate(data)
        if not result.index_dir.is_absolute():
            result = result.model_copy(update={"index_dir": ROOT / result.index_dir})
        return result
