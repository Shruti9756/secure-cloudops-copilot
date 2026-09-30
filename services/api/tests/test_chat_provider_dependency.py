from unittest.mock import Mock, sentinel

import pytest

from app.main import get_chat_provider


def test_chat_provider_still_uses_ollama_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_ollama = Mock(return_value=sentinel.chat_provider)
    monkeypatch.setattr("app.main.OllamaChatClient", create_ollama)

    assert get_chat_provider() is sentinel.chat_provider
    create_ollama.assert_called_once_with()
