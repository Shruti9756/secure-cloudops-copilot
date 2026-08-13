import json
from typing import Any, Protocol

import boto3

from app.core.config import Settings, get_settings
from app.services.embeddings import EmbeddingResult

TITAN_TEXT_EMBEDDINGS_V2_MODEL_ID = "amazon.titan-embed-text-v2:0"
TITAN_TEXT_EMBEDDINGS_V2_DIMENSIONS = 1024


class BedrockRuntimeClient(Protocol):
    """The small part of the AWS client this adapter needs.

    A protocol lets tests provide a fake client, so unit tests never call AWS.
    """

    def invoke_model(
        self,
        *,
        modelId: str,
        body: str,
        accept: str,
        contentType: str,
    ) -> dict[str, Any]: ...


class BedrockEmbeddingClient:
    """Convert text into Titan V2 embeddings through Amazon Bedrock."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: BedrockRuntimeClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()

        # Tests inject a fake client. Real local runs construct the Boto3 client.
        self._client = client or self._build_client()

    def embed(self, text: str) -> EmbeddingResult:
        """Embed one non-empty chunk using a normalized 1,024-dimension vector."""
        normalized_text = text.strip()

        if not normalized_text:
            raise ValueError("Text to embed must not be empty")

        response = self._client.invoke_model(
            modelId=TITAN_TEXT_EMBEDDINGS_V2_MODEL_ID,
            body=json.dumps(
                {
                    "inputText": normalized_text,
                    "dimensions": TITAN_TEXT_EMBEDDINGS_V2_DIMENSIONS,
                    # Normalized vectors make later cosine similarity retrieval reliable.
                    "normalize": True,
                }
            ),
            accept="application/json",
            contentType="application/json",
        )

        response_payload = json.loads(response["body"].read())
        vector = response_payload["embedding"]
        token_count = response_payload["inputTextTokenCount"]

        # Prevent invalid provider responses from being stored in our vector database.
        if not isinstance(vector, list) or len(vector) != TITAN_TEXT_EMBEDDINGS_V2_DIMENSIONS:
            raise ValueError("Bedrock returned an embedding with an unexpected dimension")

        if not isinstance(token_count, int) or token_count < 0:
            raise ValueError("Bedrock returned an invalid input token count")

        return EmbeddingResult(
            vector=[float(value) for value in vector],
            input_text_token_count=token_count,
            model_id=TITAN_TEXT_EMBEDDINGS_V2_MODEL_ID,
        )

    def _build_client(self) -> BedrockRuntimeClient:
        """Create a signed Bedrock Runtime client from the configured AWS profile."""
        session = boto3.Session(
            profile_name=self._settings.aws_profile or None,
            region_name=self._settings.aws_region,
        )

        return session.client("bedrock-runtime")
