"""OrcaRouter Cyber Inference provider support.

OrcaRouter is an OpenAI-compatible gateway for security teams: a named
provider that routes authorised, scoped security and OSINT reasoning requests
through one endpoint (``https://api.orcarouter.ai/v1``).

This module holds the parts of the integration that do not depend on
LangChain: credential/base-URL resolution, the live model catalog
(``GET /v1/models``) with capability filtering, a small verified cold-start
catalog, and error classification. Everything here is standard library only so
it can be imported (and tested) without the agent stack.

Authentication is API-key only in this project: Osintgraph has no OAuth or
browser-login seam, so the provider reuses the project's existing credential
store and never invents a PKCE flow. The key is the user's own normal
OrcaRouter API key (``sk-orca-...``) and is billed to their account.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

PROVIDER_ID = "orcarouter"
PROVIDER_LABEL = "OrcaRouter Cyber Inference"
DEFAULT_API_BASE = "https://api.orcarouter.ai/v1"
KEY_PREFIX = "sk-orca-"
KEY_DASHBOARD_URL = "https://www.orcarouter.ai/console"
PROVIDER_PAGE_URL = "https://www.orcarouter.ai/cyber"
MODEL_CATALOG_URL = "https://www.orcarouter.ai/models?tier=cyber"

DEFAULT_MODEL = "orcarouter/auto"
GENERAL_FALLBACK_MODEL = "orcarouter/fusion"
CYBER_MODELS: Tuple[str, ...] = (
    "orca/orcacyber-ultra-1.0",
    "orca/orcacyber-zero-1.5",
    "orca/orcacyber-zero-1.0",
)

#: Endpoint types a chat client in this project can speak.
TEXT_ENDPOINT_TYPES = frozenset({"openai", "anthropic", "gemini", "openai-response"})
#: Endpoint types that are never a text-chat route.
NON_TEXT_ENDPOINT_TYPES = frozenset(
    {"image-generation", "openai-video", "jina-rerank", "embeddings"}
)

#: Hard bounds so a catalog response cannot consume unbounded memory.
MAX_MODELS = 500
MAX_RESPONSE_BYTES = 1_000_000
MAX_ID_LENGTH = 200

CHAT = "chat"
MULTIMODAL = "multimodal"
EMBEDDING = "embedding"
IMAGE_GENERATION = "image"
VIDEO_GENERATION = "video"
RERANK = "rerank"

SUPPORTED_CAPABILITIES = (CHAT, MULTIMODAL, EMBEDDING, IMAGE_GENERATION, VIDEO_GENERATION, RERANK)


class OrcaRouterError(RuntimeError):
    """An error that is safe to show to a user.

    The message never contains the API key or an upstream response body.
    ``kind`` is one of ``auth``, ``rate_limit``, ``network``, ``server``,
    ``invalid_response`` or ``config``.
    """

    def __init__(self, message: str, kind: str = "server", status: Optional[int] = None):
        super().__init__(message)
        self.kind = kind
        self.status = status


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _is_loopback_host(host: str) -> bool:
    host = (host or "").strip("[]").lower()
    return host in ("localhost", "127.0.0.1", "::1")


def validate_base_url(url: str) -> str:
    """Validate an inference base URL.

    HTTPS is required for anything that is not loopback; HTTP is accepted only
    for loopback development hosts, matching the project's local-first CLI.
    """
    parsed = urllib.parse.urlsplit((url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise OrcaRouterError(
            "OrcaRouter base URL must be an absolute http(s) URL.", kind="config"
        )
    if parsed.username or parsed.password:
        raise OrcaRouterError(
            "OrcaRouter base URL must not contain userinfo.", kind="config"
        )
    if parsed.scheme == "http" and not _is_loopback_host(parsed.hostname or ""):
        raise OrcaRouterError(
            "OrcaRouter base URL must use HTTPS unless it points at loopback.",
            kind="config",
        )
    return url.rstrip("/")


def resolve_api_base(env: Optional[Dict[str, str]] = None) -> str:
    """Resolve the inference origin.

    Precedence, highest first:
    ``ORCAROUTER_API_BASE_URL`` (project-native), ``ORCA_API_BASE_URL``
    (campaign-standard), shared self-hosted ``ORCA_BASE_URL`` (``/v1``
    appended), then the official ``https://api.orcarouter.ai/v1``.

    The auth origin is deliberately not consulted here: this project uses API
    keys, and the inference origin must never be derived from the auth origin
    by swapping hostnames.
    """
    env = os.environ if env is None else env
    explicit = env.get("ORCAROUTER_API_BASE_URL") or env.get("ORCA_API_BASE_URL")
    if explicit:
        return validate_base_url(explicit)
    shared = env.get("ORCA_BASE_URL")
    if shared:
        base = shared.rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        return validate_base_url(base)
    return DEFAULT_API_BASE


def normalize_api_key(key: Optional[str]) -> str:
    return (key or "").strip()


def mask_key(key: Optional[str]) -> str:
    """Render a key for status output without exposing it."""
    key = normalize_api_key(key)
    if not key:
        return ""
    if len(key) <= 8:
        return "..." + key[-2:]
    return "..." + key[-4:]


def key_format_hint(key: Optional[str]) -> Optional[str]:
    """Return a user-facing hint when the key plainly is not an OrcaRouter key.

    The prefix is a format check only; it is not proof of validity. Validity is
    established by the first real request, never by a paid probe.
    """
    key = normalize_api_key(key)
    if key and not key.startswith(KEY_PREFIX):
        return "OrcaRouter API keys start with '{}'.".format(KEY_PREFIX)
    return None


# ---------------------------------------------------------------------------
# Model records and capability filters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelRecord:
    """A single model from the live catalog or the verified fallback seed."""

    id: str
    endpoint_types: Tuple[str, ...] = ()
    input_modalities: Tuple[str, ...] = ()
    output_modalities: Tuple[str, ...] = ()
    reasoning_efforts: Tuple[str, ...] = ()
    context_length: Optional[int] = None
    source: str = "live"
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def supports(self, capability: str) -> bool:
        return model_supports(self.id, list(self.endpoint_types),
                              list(self.input_modalities), capability,
                              record=self)


def _string_tuple(value: Any, limit: int = 32) -> Tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    out: List[str] = []
    for item in value[:limit]:
        if isinstance(item, str) and item:
            out.append(item)
    return tuple(out)


def _positive_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 0 < value <= 100_000_000:
        return value
    return None


def model_from_payload(item: Any, source: str = "live") -> Optional[ModelRecord]:
    """Parse one catalog item, rejecting anything of an unexpected shape."""
    if not isinstance(item, dict):
        return None
    model_id = item.get("id")
    if not isinstance(model_id, str) or not model_id or len(model_id) > MAX_ID_LENGTH:
        return None
    endpoint_types = _string_tuple(item.get("supported_endpoint_types"))
    architecture = item.get("architecture")
    if not isinstance(architecture, dict):
        architecture = {}
    input_modalities = _string_tuple(architecture.get("input_modalities"))
    output_modalities = _string_tuple(architecture.get("output_modalities"))
    context_length = _positive_int(
        architecture.get("context_length") or item.get("context_length")
    )
    reasoning = item.get("reasoning")
    efforts: Tuple[str, ...] = ()
    if isinstance(reasoning, dict):
        efforts = _string_tuple(reasoning.get("efforts"))
    elif isinstance(reasoning, (list, tuple)):
        efforts = _string_tuple(reasoning)
    return ModelRecord(
        id=model_id,
        endpoint_types=endpoint_types,
        input_modalities=input_modalities,
        output_modalities=output_modalities,
        reasoning_efforts=efforts,
        context_length=context_length,
        source=source,
        metadata=architecture,
    )


def _text_endpoints(endpoint_types: Iterable[str]) -> set:
    return set(endpoint_types) & TEXT_ENDPOINT_TYPES


def model_supports(
    model_id: str,
    endpoint_types: List[str],
    input_modalities: List[str],
    capability: str,
    record: Optional[ModelRecord] = None,
) -> bool:
    """Capability filter used by every model selector.

    Unknown metadata fails closed: no modality is assumed from a model name.
    """
    types = set(endpoint_types or ())
    modalities = set(input_modalities or ())
    text = _text_endpoints(types)
    is_text_chat = bool(text) and not (types and types.issubset(NON_TEXT_ENDPOINT_TYPES))

    if capability == CHAT:
        return is_text_chat
    if capability == MULTIMODAL:
        return is_text_chat and "image" in modalities
    if capability == EMBEDDING:
        return bool(types & {"embeddings", "embedding"})
    if capability == IMAGE_GENERATION:
        return "image-generation" in types
    if capability == VIDEO_GENERATION:
        return "openai-video" in types
    if capability == RERANK:
        return "jina-rerank" in types
    raise ValueError("unknown capability: {!r}".format(capability))


def filter_models(models: Iterable[ModelRecord], capability: str) -> List[ModelRecord]:
    return [
        model
        for model in models
        if model.supports(capability)
    ]


# ---------------------------------------------------------------------------
# Verified cold-start catalog
# ---------------------------------------------------------------------------

#: Small, sourced seed used when live discovery is unavailable. Ids were read
#: from ``GET https://api.orcarouter.ai/v1/models`` on 2026-10-24; modalities
#: and reasoning ladders are the verified values shipped by the project's
#: campaign seed. Anything not verified here is omitted rather than guessed,
#: and no model name is used to infer a capability.
VERIFIED_FALLBACK_MODELS: Tuple[ModelRecord, ...] = (
    ModelRecord(
        id=DEFAULT_MODEL,
        endpoint_types=("openai", "openai-response", "anthropic", "gemini"),
        input_modalities=("text",),
        output_modalities=("text",),
        source="verified-fallback:api.orcarouter.ai/v1/models@2026-10-24",
    ),
    ModelRecord(
        id=GENERAL_FALLBACK_MODEL,
        endpoint_types=("openai", "openai-response", "anthropic", "gemini"),
        input_modalities=("text",),
        output_modalities=("text",),
        source="verified-fallback:api.orcarouter.ai/v1/models@2026-10-24",
    ),
    ModelRecord(
        id="orca/orcacyber-ultra-1.0",
        endpoint_types=("openai",),
        input_modalities=("text",),
        output_modalities=("text",),
        source="verified-fallback:api.orcarouter.ai/v1/models@2026-10-24",
    ),
    ModelRecord(
        id="orca/orcacyber-zero-1.5",
        endpoint_types=("openai",),
        input_modalities=("text",),
        output_modalities=("text",),
        source="verified-fallback:api.orcarouter.ai/v1/models@2026-10-24",
    ),
    ModelRecord(
        id="orca/orcacyber-zero-1.0",
        endpoint_types=("openai",),
        input_modalities=("text",),
        output_modalities=("text",),
        source="verified-fallback:api.orcarouter.ai/v1/models@2026-10-24",
    ),
    ModelRecord(
        id="openai/gpt-5.5",
        endpoint_types=("openai", "openai-response", "anthropic"),
        input_modalities=("text",),
        output_modalities=("text",),
        reasoning_efforts=("low", "medium", "high", "xhigh"),
        source="verified-fallback:campaign-seed@2026-10-24",
    ),
    ModelRecord(
        id="anthropic/claude-opus-4.8",
        endpoint_types=("openai", "openai-response", "anthropic"),
        input_modalities=("text",),
        output_modalities=("text",),
        source="verified-fallback:campaign-seed@2026-10-24",
    ),
    ModelRecord(
        id="google/gemini-3.5-flash",
        endpoint_types=("openai", "openai-response", "gemini"),
        input_modalities=("text",),
        output_modalities=("text",),
        source="verified-fallback:campaign-seed@2026-10-24",
    ),
    ModelRecord(
        id="deepseek/deepseek-v4-pro",
        endpoint_types=("openai", "openai-response", "anthropic"),
        input_modalities=("text",),
        output_modalities=("text",),
        source="verified-fallback:campaign-seed@2026-10-24",
    ),
)


def fallback_models(capability: str) -> List[ModelRecord]:
    return filter_models(VERIFIED_FALLBACK_MODELS, capability)


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


def _sanitize(message: str, api_key: str = "") -> str:
    message = (message or "").strip()
    if api_key:
        message = message.replace(api_key, "[redacted]")
    return message[:300]


class OrcaRouterClient:
    """Minimal client for the public model catalog.

    Inference itself goes through the LangChain OpenAI-compatible client built
    in ``llm_models.py``; this class only performs discovery so credentials are
    never exposed to the model-selection UI.
    """

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: float = 10.0,
        opener: Any = None,
    ):
        self.api_key = normalize_api_key(api_key)
        self.base_url = validate_base_url(base_url or resolve_api_base())
        self.timeout = timeout
        self._opener = opener or urllib.request.urlopen

    # -- internal ---------------------------------------------------------
    def _request_json(self, path: str, params: Optional[Dict[str, str]] = None) -> Any:
        url = self.base_url.rstrip("/") + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with self._opener(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = getattr(exc, "code", None)
            if status in (401, 403):
                raise OrcaRouterError(
                    "OrcaRouter rejected the API key (HTTP {}). Check the key at {} "
                    "or run `osintgraph setup orcarouter`.".format(status, KEY_DASHBOARD_URL),
                    kind="auth",
                    status=status,
                ) from None
            if status == 429:
                raise OrcaRouterError(
                    "OrcaRouter rate limited the model catalog request (HTTP 429). "
                    "Retry shortly; the verified fallback catalog is still usable.",
                    kind="rate_limit",
                    status=status,
                ) from None
            raise OrcaRouterError(
                "OrcaRouter model catalog request failed (HTTP {}).".format(status),
                kind="server",
                status=status,
            ) from None
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
            raise OrcaRouterError(
                "Could not reach the OrcaRouter model catalog: {}.".format(
                    _sanitize(str(getattr(exc, "reason", exc)), self.api_key)
                ),
                kind="network",
            ) from None

        if len(raw) > MAX_RESPONSE_BYTES:
            raise OrcaRouterError(
                "OrcaRouter model catalog response exceeded the size limit.",
                kind="invalid_response",
            )
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise OrcaRouterError(
                "OrcaRouter model catalog returned malformed JSON.",
                kind="invalid_response",
            ) from None

    # -- public -----------------------------------------------------------
    def list_models(self, capability: str = CHAT) -> List[ModelRecord]:
        if capability not in SUPPORTED_CAPABILITIES:
            raise ValueError("unknown capability: {!r}".format(capability))
        payload = self._request_json("/models")
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise OrcaRouterError(
                "OrcaRouter model catalog response has an unexpected shape.",
                kind="invalid_response",
            )
        records: List[ModelRecord] = []
        for item in payload["data"][:MAX_MODELS]:
            record = model_from_payload(item)
            if record is not None:
                records.append(record)
        return filter_models(records, capability)


# ---------------------------------------------------------------------------
# Catalog with last-known-good persistence
# ---------------------------------------------------------------------------


@dataclass
class CatalogResult:
    models: List[ModelRecord]
    source: str  # "live" | "last_known_good" | "verified_fallback"
    degraded: bool = False
    error: Optional[str] = None


class ModelCatalog:
    """Loads the live catalog, falling back to last-known-good then the seed.

    Live discovery is authoritative. The fallback seed is never mixed into a
    successful live result.
    """

    def __init__(self, cache_path: Optional[str] = None):
        self.cache_path = cache_path
        self._memory: Dict[str, List[ModelRecord]] = {}

    def _read_cache(self) -> Dict[str, List[ModelRecord]]:
        if not self.cache_path or not os.path.exists(self.cache_path):
            return {}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return {}
        if not isinstance(payload, dict):
            return {}
        cached: Dict[str, List[ModelRecord]] = {}
        for capability, items in payload.items():
            if capability not in SUPPORTED_CAPABILITIES or not isinstance(items, list):
                continue
            records = [
                record
                for record in (model_from_payload(item, source="last_known_good") for item in items[:MAX_MODELS])
                if record is not None
            ]
            cached[capability] = filter_models(records, capability)
        return cached

    def _write_cache(self, capability: str, models: List[ModelRecord]) -> None:
        if not self.cache_path:
            return
        cached = self._read_cache()
        cached[capability] = models
        payload = {
            capability: [
                {
                    "id": model.id,
                    "supported_endpoint_types": list(model.endpoint_types),
                    "architecture": {
                        "input_modalities": list(model.input_modalities),
                        "output_modalities": list(model.output_modalities),
                    },
                }
                for model in items
            ]
            for capability, items in cached.items()
        }
        try:
            directory = os.path.dirname(self.cache_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        except OSError:
            # A read-only config directory must not break discovery.
            pass

    def load(
        self,
        capability: str = CHAT,
        api_key: str = "",
        refresh: bool = False,
    ) -> CatalogResult:
        if capability not in self._memory or refresh:
            if api_key:
                try:
                    models = OrcaRouterClient(api_key).list_models(capability)
                except OrcaRouterError as exc:
                    return self._degraded(capability, exc)
                self._memory[capability] = models
                self._write_cache(capability, models)
                return CatalogResult(models=list(models), source="live")
            return self._degraded(capability, None)
        models = self._memory[capability]
        return CatalogResult(models=list(models), source="live")

    def _degraded(self, capability: str, exc: Optional[OrcaRouterError]) -> CatalogResult:
        error = str(exc) if exc else None
        cached = self._read_cache().get(capability)
        if cached:
            return CatalogResult(
                models=cached, source="last_known_good", degraded=True, error=error
            )
        return CatalogResult(
            models=fallback_models(capability),
            source="verified_fallback",
            degraded=True,
            error=error,
        )


# ---------------------------------------------------------------------------
# Selection helpers (used by the terminal model selector and tests)
# ---------------------------------------------------------------------------


def get_model(models: Iterable[ModelRecord], model_id: str) -> Optional[ModelRecord]:
    for model in models:
        if model.id == model_id:
            return model
    return None


def resolve_selected_model(
    preferred: Optional[str],
    models: Iterable[ModelRecord],
    capability: str = CHAT,
    default: str = DEFAULT_MODEL,
) -> Tuple[str, bool]:
    """Validate a stored model id against the current catalog.

    Returns ``(model_id, was_reset)``. A stored value that is no longer
    compatible is dropped, not silently kept, so callers can tell the user to
    pick again.
    """
    models = list(models)
    preferred = normalize_api_key(preferred)
    if preferred and get_model(models, preferred) is not None:
        return preferred, False
    if get_model(models, default) is not None:
        return default, bool(preferred)
    compatible = filter_models(models, capability)
    if compatible:
        return compatible[0].id, bool(preferred)
    return "", bool(preferred)


def describe_model(model: ModelRecord) -> str:
    details = []
    if model.input_modalities:
        details.append("in:" + ",".join(model.input_modalities))
    if model.reasoning_efforts:
        details.append("reasoning:" + ",".join(model.reasoning_efforts))
    if model.context_length:
        details.append("ctx:" + str(model.context_length))
    return "{} ({})".format(model.id, " ".join(details)) if details else model.id
