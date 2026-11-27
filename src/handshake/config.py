import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_PLACEHOLDER_KEY = "ollama"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_KEY_ENV = "GROQ_API_KEY"
DEFAULT_MAX_OUTPUT_TOKENS = 400


class ConfigError(Exception):
    pass


class ModelConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: Literal["ollama", "groq"]
    model: str
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


def pydantic_model(cfg: ModelConfig) -> OpenAIChatModel:
    if cfg.provider == "ollama":
        provider = OpenAIProvider(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_PLACEHOLDER_KEY)
        return OpenAIChatModel(cfg.model, provider=provider)
    api_key = os.environ.get(GROQ_KEY_ENV)
    if not api_key:
        raise ConfigError(f"{GROQ_KEY_ENV} is not set")
    return OpenAIChatModel(
        cfg.model, provider=OpenAIProvider(base_url=GROQ_BASE_URL, api_key=api_key)
    )


def litellm_id(cfg: ModelConfig) -> str:
    prefix = "ollama_chat" if cfg.provider == "ollama" else "groq"
    return f"{prefix}/{cfg.model}"


def load_models(path: Path) -> list[ModelConfig]:
    data = tomllib.loads(path.read_text())
    return [ModelConfig.model_validate(entry) for entry in data.get("models", [])]
