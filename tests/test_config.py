from pathlib import Path

import pytest
from pydantic import ValidationError

from handshake.config import ConfigError, ModelConfig, litellm_id, load_models, pydantic_model


def test_groq_without_key_raises_config_error_naming_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="GROQ_API_KEY"):
        pydantic_model(ModelConfig(provider="groq", model="m"))


def test_groq_with_key_builds_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    assert pydantic_model(ModelConfig(provider="groq", model="m")).model_name == "m"


def test_ollama_needs_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert pydantic_model(ModelConfig(provider="ollama", model="m")).model_name == "m"


def test_litellm_id_per_provider() -> None:
    assert litellm_id(ModelConfig(provider="ollama", model="a")) == "ollama_chat/a"
    assert litellm_id(ModelConfig(provider="groq", model="b")) == "groq/b"


def test_label_and_default_tokens() -> None:
    cfg = ModelConfig(provider="groq", model="b")
    assert cfg.label == "groq:b"
    assert cfg.max_output_tokens == 400


def test_load_models_from_toml(tmp_path: Path) -> None:
    path = tmp_path / "models.toml"
    path.write_text(
        '[[models]]\nprovider = "ollama"\nmodel = "a"\n\n'
        '[[models]]\nprovider = "groq"\nmodel = "b"\nmax_output_tokens = 200\n'
    )
    models = load_models(path)
    assert [m.label for m in models] == ["ollama:a", "groq:b"]
    assert models[1].max_output_tokens == 200


def test_unknown_provider_rejected(tmp_path: Path) -> None:
    path = tmp_path / "models.toml"
    path.write_text('[[models]]\nprovider = "nope"\nmodel = "a"\n')
    with pytest.raises(ValidationError):
        load_models(path)
