"""Shared test fixtures.

Every test runs against an isolated credential file and catalog cache so the
developer's real configuration is never read, written, or printed.
"""

import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="osintgraph-tests-")
os.environ.setdefault("OSINTGRAPH_CREDENTIALS_FILE", os.path.join(_TMP_DIR, "credentials.json"))
os.environ.setdefault("OSINTGRAPH_MODEL_CATALOG_CACHE", os.path.join(_TMP_DIR, "models.json"))

#: The live smoke test is the only place a real key may be used. Capture it
#: once, then keep it away from every unit test.
LIVE_API_KEY = os.environ.pop("ORCAROUTER_API_KEY", "")
os.environ.pop("ORCA_BASE_URL", None)
os.environ.pop("ORCA_API_BASE_URL", None)
os.environ.pop("ORCAROUTER_API_BASE_URL", None)

# The CI sandbox exports a SOCKS proxy for general traffic while excluding the
# OrcaRouter API host from it. httpx (used by the OpenAI-compatible client)
# refuses to build a transport for a SOCKS URL without an optional dependency,
# so tests clear the proxy variables and rely on the same direct route.
for _proxy_var in ("ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
    os.environ.pop(_proxy_var, None)


def pytest_configure(config):
    config._osintgraph_live_key = LIVE_API_KEY


CATALOG_PAYLOAD = {
    "object": "list",
    "success": True,
    "data": [
        {
            "id": "orcarouter/auto",
            "supported_endpoint_types": ["openai", "openai-response", "anthropic", "gemini"],
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        },
        {
            "id": "orcarouter/fusion",
            "supported_endpoint_types": ["openai", "openai-response", "anthropic", "gemini"],
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        },
        {
            "id": "orca/orcacyber-ultra-1.0",
            "supported_endpoint_types": ["openai"],
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        },
        {
            "id": "vendor/text-chat",
            "supported_endpoint_types": ["openai"],
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        },
        {
            "id": "vendor/gemini-chat",
            "supported_endpoint_types": ["gemini"],
            "architecture": {
                "input_modalities": ["text", "image"],
                "output_modalities": ["text"],
            },
        },
        {
            "id": "vendor/responses-chat",
            "supported_endpoint_types": ["openai-response"],
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        },
        {
            "id": "vendor/vision-chat",
            "supported_endpoint_types": ["openai", "anthropic"],
            "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
        },
        {
            "id": "vendor/undeclared-chat",
            "supported_endpoint_types": ["openai"],
        },
        {
            "id": "vendor/embed",
            "supported_endpoint_types": ["embeddings"],
            "architecture": {"input_modalities": ["text"], "output_modalities": ["embedding"]},
        },
        {
            "id": "vendor/image-gen",
            "supported_endpoint_types": ["image-generation"],
            "architecture": {"input_modalities": ["text"], "output_modalities": ["image"]},
        },
        {
            "id": "vendor/video-gen",
            "supported_endpoint_types": ["openai-video"],
            "architecture": {"input_modalities": ["text"], "output_modalities": ["video"]},
        },
        {
            "id": "vendor/rerank",
            "supported_endpoint_types": ["jina-rerank"],
            "architecture": {"input_modalities": ["text"], "output_modalities": ["score"]},
        },
        {"supported_endpoint_types": ["openai"], "architecture": {"input_modalities": ["text"]}},
        "not-a-dict",
    ],
}


def catalog_payload():
    return {
        "object": CATALOG_PAYLOAD["object"],
        "success": CATALOG_PAYLOAD["success"],
        "data": [dict(item) if isinstance(item, dict) else item for item in CATALOG_PAYLOAD["data"]],
    }
