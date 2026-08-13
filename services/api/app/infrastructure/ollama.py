import json
from collections.abc import Callable
from typing import Any
from urllib.request import Request, urlopen

from app.core.config import Settings, get_settings
from app.services.embeddings import EmbeddingResult

OLLAMA_MXBAI_EMBED_LARGE_MODEL_ID = "mxbai-embed-large"
OLLAMA_MXBAI_EMBED_LARGE_DIMENSIONS = 1024

JsonObject = dict[str, Any]
PostJson = Callable[[str, JsonObject], JsonObject]


class OllamaEmbeddingClient:
    """Convert text into local mxbai embeddings through Ollama's HTTP API."""

    def __init__(
        self,
        settings: Settings | None = None,
        post_json: PostJson | None = None,
    ) -> None:
        self._settings = settings or get_settings()

        # Tests inject a fake function; real runs use Python's built-in HTTP client.
        self._post_json = post_json or _post_json

    def embed(self, text: str) -> EmbeddingResult:
        """Embed one non-empty chunk with the local 1,024-dimension model."""
        normalized_text = text.strip()

        if not normalized_text:
            raise ValueError("Text to embed must not be empty")

        response_payload = self._post_json(
            f"{self._settings.ollama_base_url.rstrip('/')}/api/embed",
            {
                "model": OLLAMA_MXBAI_EMBED_LARGE_MODEL_ID,
                "input": normalized_text,
                # Keep the model loaded during a small batch, then release memory automatically.
                "keep_alive": "5m",
            },
        )

        embeddings = response_payload.get("embeddings")

        # A single input string must produce exactly one numeric vector.
        if (
            not isinstance(embeddings, list)
            or len(embeddings) != 1
            or not isinstance(embeddings[0], list)
        ):
            raise ValueError("Ollama returned an invalid embeddings response")

        vector = embeddings[0]

        if len(vector) != OLLAMA_MXBAI_EMBED_LARGE_DIMENSIONS:
            raise ValueError("Ollama returned an embedding with an unexpected dimension")

        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in vector):
            raise ValueError("Ollama returned a non-numeric embedding value")

        token_count = response_payload.get("prompt_eval_count")

        if isinstance(token_count, bool) or not isinstance(token_count, int) or token_count < 0:
            raise ValueError("Ollama returned an invalid input token count")

        model_id = response_payload.get("model")

        if model_id != OLLAMA_MXBAI_EMBED_LARGE_MODEL_ID:
            raise ValueError("Ollama returned an unexpected embedding model")

        return EmbeddingResult(
            vector=[float(value) for value in vector],
            input_text_token_count=token_count,
            model_id=model_id,
        )


def _post_json(url: str, payload: JsonObject) -> JsonObject:
    """Send one JSON request to the local Ollama service."""
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    # The model can take a little time to load on CPU during the first request.
    with urlopen(request, timeout=90) as response:
        response_payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(response_payload, dict):
        raise TypeError("Ollama returned a non-object JSON response")

    return response_payload
