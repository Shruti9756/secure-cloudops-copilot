from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.main import get_embedding_provider


@pytest.mark.parametrize("selected_backend", ["ollama", "bedrock"])
def test_api_selects_configured_embedding_provider(
    monkeypatch: pytest.MonkeyPatch,
    selected_backend: str,
) -> None:
    ollama_provider = object()
    bedrock_provider = object()
    create_ollama = Mock(return_value=ollama_provider)
    create_bedrock = Mock(return_value=bedrock_provider)

    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: SimpleNamespace(embedding_provider=selected_backend),
    )
    monkeypatch.setattr("app.main.OllamaEmbeddingClient", create_ollama)
    monkeypatch.setattr("app.main.BedrockEmbeddingClient", create_bedrock)

    result = get_embedding_provider()

    if selected_backend == "bedrock":
        assert result is bedrock_provider
        create_bedrock.assert_called_once_with()
        create_ollama.assert_not_called()
    else:
        assert result is ollama_provider
        create_ollama.assert_called_once_with()
        create_bedrock.assert_not_called()
