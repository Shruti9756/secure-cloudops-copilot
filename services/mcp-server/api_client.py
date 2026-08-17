"""Controlled HTTP adapter for approved SecureCloudOps FastAPI endpoints."""

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from re import fullmatch
from typing import Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
ASK_ENDPOINT_PATH = "/api/v1/ask"
DEPLOYMENT_ENDPOINT_PATH = "/api/v1/deployments"
DEFAULT_TIMEOUT_SECONDS = 60

# These patterns prevent MCP tool arguments from becoming arbitrary URL paths.
SERVICE_NAME_PATTERN = r"[a-z][a-z0-9-]{0,62}"
SEMANTIC_VERSION_PATTERN = r"\d+\.\d+\.\d+"


class SecureCloudOpsApiUnavailableError(Exception):
    """Raised when the local API cannot be reached safely."""


class SecureCloudOpsApiProtocolError(Exception):
    """Raised when the API returns a response outside the expected contract."""


class SecureCloudOpsApiRequestError(Exception):
    """Raised when the guarded API rejects an otherwise valid tool request."""

    def __init__(
        self,
        *,
        status_code: int,
        detail: str,
        retry_after_seconds: int | None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class JsonHttpResponse:
    """A parsed JSON response plus safe HTTP metadata needed by the MCP layer."""

    status_code: int
    payload: dict[str, object]
    headers: Mapping[str, str]


class JsonHttpTransport(Protocol):
    """Small transport interface that makes the adapter independent from urllib."""

    def post_json(
        self,
        *,
        url: str,
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> JsonHttpResponse:
        """POST one JSON object and return a parsed JSON response."""

    def get_json(
        self,
        *,
        url: str,
        timeout_seconds: int,
    ) -> JsonHttpResponse:
        """GET one JSON object and return a parsed JSON response."""


class UrllibJsonHttpTransport:
    """Standard-library HTTP transport used in local development and containers."""

    def post_json(
        self,
        *,
        url: str,
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> JsonHttpResponse:
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return self._send_request(request=request, timeout_seconds=timeout_seconds)

    def get_json(
        self,
        *,
        url: str,
        timeout_seconds: int,
    ) -> JsonHttpResponse:
        request = Request(
            url,
            headers={"Accept": "application/json"},
            method="GET",
        )
        return self._send_request(request=request, timeout_seconds=timeout_seconds)

    def _send_request(
        self,
        *,
        request: Request,
        timeout_seconds: int,
    ) -> JsonHttpResponse:
        """Send one fixed request and convert success or HTTP errors to safe data."""
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return JsonHttpResponse(
                    status_code=response.status,
                    payload=_decode_json_object(response.read()),
                    headers=dict(response.headers.items()),
                )
        except HTTPError as error:
            # HTTP errors still contain a useful JSON body and safe response headers.
            return JsonHttpResponse(
                status_code=error.code,
                payload=_decode_json_object(error.read()),
                headers=dict(error.headers.items()) if error.headers is not None else {},
            )
        except (URLError, TimeoutError) as error:
            raise SecureCloudOpsApiUnavailableError(
                "The SecureCloudOps API is unavailable."
            ) from error


@dataclass(frozen=True)
class ApiSource:
    """One safe citation source returned by the guarded API."""

    source_identifier: str
    document_title: str
    cosine_distance: float


@dataclass(frozen=True)
class GuardedApiAnswer:
    """Validated, client-safe subset of the API RAG response."""

    status: Literal[
        "grounded",
        "insufficient_evidence",
        "citation_validation_failed",
    ]
    answer: str
    tenant: str
    embedding_model: str
    generation_model: str | None
    sources: tuple[ApiSource, ...]
    cache_status: str | None


@dataclass(frozen=True)
class DeploymentContext:
    """One approved deployment record retrieved through the fixed API route."""

    tenant: str
    service: str
    version: str
    title: str
    source_identifier: str
    content: str


class SecureCloudOpsApiClient:
    """Adapter that permits MCP tools to call only approved guarded API routes."""

    def __init__(
        self,
        *,
        api_base_url: str | None = None,
        transport: JsonHttpTransport | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        configured_base_url = (
            api_base_url or os.environ.get("SECURE_CLOUDOPS_API_BASE_URL") or DEFAULT_API_BASE_URL
        ).strip()

        if not configured_base_url:
            raise ValueError("SecureCloudOps API base URL must not be empty")

        if not isinstance(timeout_seconds, int):
            raise TypeError("API timeout must be an integer")

        if timeout_seconds <= 0:
            raise ValueError("API timeout must be a positive integer")

        self._api_base_url = configured_base_url.rstrip("/")
        self._transport = transport or UrllibJsonHttpTransport()
        self._timeout_seconds = timeout_seconds

    def ask(self, *, question: str, limit: int) -> GuardedApiAnswer:
        """Call the one approved RAG endpoint with a bounded request shape."""
        response = self._transport.post_json(
            url=f"{self._api_base_url}{ASK_ENDPOINT_PATH}",
            payload={"question": question, "limit": limit},
            timeout_seconds=self._timeout_seconds,
        )

        if response.status_code != 200:
            raise SecureCloudOpsApiRequestError(
                status_code=response.status_code,
                detail=_read_error_detail(response.payload),
                retry_after_seconds=_read_optional_header_int(
                    response.headers,
                    "Retry-After",
                ),
            )

        return _parse_guarded_answer(response)

    def get_deployment_context(
        self,
        *,
        service: str,
        version: str,
    ) -> DeploymentContext:
        """Retrieve one approved deployment record through the fixed GET route."""
        validated_service = _validate_service_name(service)
        validated_version = _validate_semantic_version(version)

        response = self._transport.get_json(
            url=(
                f"{self._api_base_url}{DEPLOYMENT_ENDPOINT_PATH}/"
                f"{validated_service}/{validated_version}"
            ),
            timeout_seconds=self._timeout_seconds,
        )

        if response.status_code != 200:
            raise SecureCloudOpsApiRequestError(
                status_code=response.status_code,
                detail=_read_error_detail(response.payload),
                retry_after_seconds=_read_optional_header_int(
                    response.headers,
                    "Retry-After",
                ),
            )

        deployment_context = _parse_deployment_context(response)

        # A mismatched response must never be returned under the requested identity.
        if (
            deployment_context.service != validated_service
            or deployment_context.version != validated_version
        ):
            raise SecureCloudOpsApiProtocolError(
                "SecureCloudOps API returned mismatched deployment context."
            )

        return deployment_context


def _validate_service_name(service: str) -> str:
    """Accept only a lowercase service identifier, never a raw URL segment."""
    if not isinstance(service, str):
        raise TypeError("Service must be a string")

    normalized_service = service.strip()

    if not fullmatch(SERVICE_NAME_PATTERN, normalized_service):
        raise ValueError("Service must use lowercase letters, numbers, and hyphens only.")

    return normalized_service


def _validate_semantic_version(version: str) -> str:
    """Accept only a simple semantic version, never a raw URL segment."""
    if not isinstance(version, str):
        raise TypeError("Version must be a string")

    normalized_version = version.strip()

    if not fullmatch(SEMANTIC_VERSION_PATTERN, normalized_version):
        raise ValueError("Version must use the form major.minor.patch")

    return normalized_version


def _decode_json_object(raw_body: bytes) -> dict[str, object]:
    """Decode an HTTP JSON body and reject unexpected JSON shapes."""
    try:
        decoded = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SecureCloudOpsApiProtocolError("SecureCloudOps API returned invalid JSON.") from error

    if not isinstance(decoded, dict):
        raise SecureCloudOpsApiProtocolError(
            "SecureCloudOps API returned a non-object JSON response."
        )

    return decoded


def _parse_guarded_answer(response: JsonHttpResponse) -> GuardedApiAnswer:
    """Validate the API response before an MCP tool can return it to a host."""
    status = _required_string(response.payload, "status")

    if status not in {
        "grounded",
        "insufficient_evidence",
        "citation_validation_failed",
    }:
        raise SecureCloudOpsApiProtocolError("SecureCloudOps API returned an unknown status.")

    generation_model = response.payload.get("generation_model")

    if generation_model is not None and not isinstance(generation_model, str):
        raise SecureCloudOpsApiProtocolError(
            "SecureCloudOps API returned an invalid generation model."
        )

    raw_sources = response.payload.get("sources")

    if not isinstance(raw_sources, list):
        raise SecureCloudOpsApiProtocolError("SecureCloudOps API returned invalid source metadata.")

    return GuardedApiAnswer(
        status=status,
        answer=_required_string(response.payload, "answer"),
        tenant=_required_string(response.payload, "tenant"),
        embedding_model=_required_string(response.payload, "embedding_model"),
        generation_model=generation_model,
        sources=tuple(_parse_source(raw_source) for raw_source in raw_sources),
        cache_status=_read_optional_header(response.headers, "X-Cache"),
    )


def _parse_deployment_context(response: JsonHttpResponse) -> DeploymentContext:
    """Validate a deterministic deployment-context response before MCP uses it."""
    return DeploymentContext(
        tenant=_required_string(response.payload, "tenant"),
        service=_required_string(response.payload, "service"),
        version=_required_string(response.payload, "version"),
        title=_required_string(response.payload, "title"),
        source_identifier=_required_string(response.payload, "source_identifier"),
        content=_required_string(response.payload, "content"),
    )


def _parse_source(raw_source: object) -> ApiSource:
    """Validate one citation source without exposing raw vector or chunk data."""
    if not isinstance(raw_source, dict):
        raise SecureCloudOpsApiProtocolError("SecureCloudOps API returned a non-object source.")

    raw_distance = raw_source.get("cosine_distance")

    if not isinstance(raw_distance, (int, float)) or isinstance(raw_distance, bool):
        raise SecureCloudOpsApiProtocolError(
            "SecureCloudOps API returned an invalid cosine distance."
        )

    return ApiSource(
        source_identifier=_required_string(raw_source, "source_identifier"),
        document_title=_required_string(raw_source, "document_title"),
        cosine_distance=float(raw_distance),
    )


def _required_string(payload: Mapping[str, object], field_name: str) -> str:
    """Read a non-empty string from an API payload."""
    value = payload.get(field_name)

    if not isinstance(value, str) or not value.strip():
        raise SecureCloudOpsApiProtocolError(
            f"SecureCloudOps API returned an invalid {field_name}."
        )

    return value


def _read_error_detail(payload: Mapping[str, object]) -> str:
    """Return only a safe API error detail, never raw transport exception text."""
    detail = payload.get("detail")

    if isinstance(detail, str) and detail.strip():
        return detail

    return "The SecureCloudOps API rejected the request."


def _read_optional_header(
    headers: Mapping[str, str],
    header_name: str,
) -> str | None:
    """Read a header without assuming a particular HTTP header casing."""
    for current_name, value in headers.items():
        if current_name.casefold() == header_name.casefold():
            return value

    return None


def _read_optional_header_int(
    headers: Mapping[str, str],
    header_name: str,
) -> int | None:
    """Read a non-negative integer header such as Retry-After."""
    raw_value = _read_optional_header(headers, header_name)

    if raw_value is None:
        return None

    try:
        parsed_value = int(raw_value)
    except ValueError:
        return None

    return parsed_value if parsed_value >= 0 else None
