"""Catalog, capability-filter and fallback tests for the OrcaRouter provider."""

import json
import urllib.error

import pytest

from conftest import catalog_payload
from osintgraph.services import orcarouter
from osintgraph.services.orcarouter import (
    CHAT,
    EMBEDDING,
    IMAGE_GENERATION,
    MULTIMODAL,
    RERANK,
    VIDEO_GENERATION,
    ModelCatalog,
    ModelRecord,
    OrcaRouterClient,
    OrcaRouterError,
    filter_models,
    model_from_payload,
    resolve_selected_model,
)


class FakeResponse:
    def __init__(self, body, status=200):
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.status = status

    def read(self, size=-1):
        if size is None or size < 0:
            return self._body
        return self._body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        return None


def opener(body=None, error=None, record=None):
    def _open(request, timeout=None):
        if record is not None:
            record.append(request)
        if error is not None:
            raise error
        return FakeResponse(body)

    return _open


def http_error(status):
    return urllib.error.HTTPError(
        "https://api.orcarouter.ai/v1/models",
        status,
        "error",
        {},
        FakeResponse({"error": "boom"}),
    )


def records():
    return [
        record
        for record in (model_from_payload(item) for item in catalog_payload()["data"])
        if record is not None
    ]


# ---------------------------------------------------------------------------
# Capability filters
# ---------------------------------------------------------------------------


def test_chat_filter_keeps_text_endpoints_and_drops_specialised_models():
    ids = [m.id for m in filter_models(records(), CHAT)]
    assert "vendor/text-chat" in ids
    assert "vendor/gemini-chat" in ids
    assert "vendor/responses-chat" in ids
    assert "vendor/vision-chat" in ids
    for excluded in (
        "vendor/embed",
        "vendor/image-gen",
        "vendor/video-gen",
        "vendor/rerank",
    ):
        assert excluded not in ids


def test_multimodal_filter_requires_declared_image_input():
    ids = [m.id for m in filter_models(records(), MULTIMODAL)]
    assert ids == ["vendor/gemini-chat", "vendor/vision-chat"]
    # A model with no architecture metadata must fail closed, not be assumed.
    assert "vendor/undeclared-chat" not in ids


def test_embedding_image_video_rerank_filters_are_strict():
    assert [m.id for m in filter_models(records(), EMBEDDING)] == ["vendor/embed"]
    assert [m.id for m in filter_models(records(), IMAGE_GENERATION)] == ["vendor/image-gen"]
    assert [m.id for m in filter_models(records(), VIDEO_GENERATION)] == ["vendor/video-gen"]
    assert [m.id for m in filter_models(records(), RERANK)] == ["vendor/rerank"]


def test_model_without_text_endpoint_is_not_a_chat_model():
    record = ModelRecord(id="vendor/unknown", endpoint_types=())
    assert not record.supports(CHAT)
    assert not record.supports(MULTIMODAL)


def test_malformed_catalog_items_are_rejected():
    assert model_from_payload({"no-id": True}) is None
    assert model_from_payload({"id": ""}) is None
    assert model_from_payload({"id": "x" * 500}) is None
    assert model_from_payload("not-a-dict") is None


# ---------------------------------------------------------------------------
# HTTP client behaviour
# ---------------------------------------------------------------------------


def test_client_returns_filtered_models():
    client = OrcaRouterClient("sk-orca-test", opener=opener(catalog_payload()))
    ids = [m.id for m in client.list_models(CHAT)]
    assert "vendor/text-chat" in ids
    assert "vendor/image-gen" not in ids


def test_client_sends_bearer_token_and_inference_origin():
    seen = []
    client = OrcaRouterClient(
        "sk-orca-test", base_url="https://api.orcarouter.ai/v1", opener=opener(catalog_payload(), record=seen)
    )
    client.list_models(CHAT)
    assert len(seen) == 1
    request = seen[0]
    assert request.full_url == "https://api.orcarouter.ai/v1/models"
    assert request.get_header("Authorization") == "Bearer sk-orca-test"


def test_client_handles_empty_api_key_without_leaking_it():
    seen = []
    client = OrcaRouterClient("", opener=opener(catalog_payload(), record=seen))
    client.list_models(CHAT)
    assert seen[0].get_header("Authorization") is None


def test_client_classifies_auth_rate_limit_and_network_errors_without_key():
    key = "sk-orca-secretvalue"
    with pytest.raises(OrcaRouterError) as auth:
        OrcaRouterClient(key, opener=opener(error=http_error(401))).list_models(CHAT)
    assert auth.value.kind == "auth"
    assert key not in str(auth.value)

    for status, kind in ((403, "auth"), (429, "rate_limit"), (500, "server")):
        with pytest.raises(OrcaRouterError) as err:
            OrcaRouterClient(key, opener=opener(error=http_error(status))).list_models(CHAT)
        assert err.value.kind == kind
        assert key not in str(err.value)

    with pytest.raises(OrcaRouterError) as network:
        OrcaRouterClient(key, opener=opener(error=urllib.error.URLError("down"))).list_models(CHAT)
    assert network.value.kind == "network"
    assert key not in str(network.value)


def test_client_rejects_malformed_json():
    with pytest.raises(OrcaRouterError) as err:
        OrcaRouterClient("sk-orca-test", opener=opener(b"<html>")).list_models(CHAT)
    assert err.value.kind == "invalid_response"


def test_client_rejects_oversized_catalog_response():
    body = b'{"data":[],"padding":"' + b"x" * (orcarouter.MAX_RESPONSE_BYTES + 10) + b'"}'
    with pytest.raises(OrcaRouterError) as err:
        OrcaRouterClient("sk-orca-test", opener=opener(body)).list_models(CHAT)
    assert err.value.kind == "invalid_response"


def test_client_bounds_model_count():
    payload = catalog_payload()
    payload["data"] = [
        {"id": "vendor/model-{}".format(i), "supported_endpoint_types": ["openai"]}
        for i in range(orcarouter.MAX_MODELS + 50)
    ]
    models = OrcaRouterClient("sk-orca-test", opener=opener(payload)).list_models(CHAT)
    assert len(models) == orcarouter.MAX_MODELS


# ---------------------------------------------------------------------------
# Base URL policy
# ---------------------------------------------------------------------------


def test_api_base_precedence_and_shared_fallback():
    default = orcarouter.resolve_api_base({})
    assert default == "https://api.orcarouter.ai/v1"

    shared = orcarouter.resolve_api_base({"ORCA_BASE_URL": "https://orca.internal"})
    assert shared == "https://orca.internal/v1"

    standard = orcarouter.resolve_api_base(
        {"ORCA_BASE_URL": "https://shared", "ORCA_API_BASE_URL": "https://api.standard/v1"}
    )
    assert standard == "https://api.standard/v1"

    native = orcarouter.resolve_api_base(
        {
            "ORCA_API_BASE_URL": "https://api.standard/v1",
            "ORCAROUTER_API_BASE_URL": "https://api.native/v1",
        }
    )
    assert native == "https://api.native/v1"


def test_api_base_requires_https_except_loopback():
    with pytest.raises(OrcaRouterError) as err:
        orcarouter.resolve_api_base({"ORCAROUTER_API_BASE_URL": "http://orca.example.com/v1"})
    assert err.value.kind == "config"
    assert (
        orcarouter.resolve_api_base({"ORCAROUTER_API_BASE_URL": "http://127.0.0.1:8080/v1"})
        == "http://127.0.0.1:8080/v1"
    )
    with pytest.raises(OrcaRouterError):
        orcarouter.resolve_api_base({"ORCAROUTER_API_BASE_URL": "https://user:pass@orca.example.com/v1"})


def test_inference_origin_is_never_derived_from_the_auth_origin():
    assert "www.orcarouter.ai" not in orcarouter.DEFAULT_API_BASE
    assert orcarouter.DEFAULT_API_BASE == "https://api.orcarouter.ai/v1"


# ---------------------------------------------------------------------------
# Catalog: live, last-known-good, verified fallback
# ---------------------------------------------------------------------------


def test_catalog_marks_live_result_authoritative_and_does_not_mix_seed(tmp_path):
    cache = str(tmp_path / "catalog.json")
    catalog = ModelCatalog(cache)

    import osintgraph.services.orcarouter as module

    original = module.OrcaRouterClient

    class StubClient:
        def __init__(self, api_key, **kwargs):
            self.api_key = api_key

        def list_models(self, capability):
            return [m for m in records() if m.supports(capability)]

    try:
        module.OrcaRouterClient = StubClient
        result = catalog.load(CHAT, api_key="sk-orca-test")
    finally:
        module.OrcaRouterClient = original

    assert result.source == "live"
    assert not result.degraded
    ids = {m.id for m in result.models}
    assert "vendor/text-chat" in ids
    # The seed must never be appended to a successful live result.
    assert "openai/gpt-5.5" not in ids
    assert ids == {m.id for m in records() if m.supports(CHAT)}


def test_catalog_falls_back_to_last_known_good(tmp_path, monkeypatch):
    cache = str(tmp_path / "catalog.json")
    catalog = ModelCatalog(cache)

    class Live:
        def __init__(self, api_key, **kwargs):
            pass

        def list_models(self, capability):
            return [m for m in records() if m.supports(capability)]

    monkeypatch.setattr(orcarouter, "OrcaRouterClient", Live)
    first = catalog.load(CHAT, api_key="sk-orca-test")
    assert first.source == "live"

    freshed = ModelCatalog(cache)

    def broken(api_key, **kwargs):
        raise OrcaRouterError("catalog down", kind="network")

    monkeypatch.setattr(orcarouter, "OrcaRouterClient", broken)
    second = freshed.load(CHAT, api_key="sk-orca-test")
    assert second.source == "last_known_good"
    assert second.degraded
    assert {m.id for m in second.models} == {m.id for m in first.models}


def test_catalog_falls_back_to_verified_seed_without_cache(tmp_path, monkeypatch):
    catalog = ModelCatalog(str(tmp_path / "missing.json"))

    def broken(api_key, **kwargs):
        raise OrcaRouterError("catalog down", kind="network")

    monkeypatch.setattr(orcarouter, "OrcaRouterClient", broken)
    result = catalog.load(CHAT, api_key="sk-orca-test")
    assert result.source == "verified_fallback"
    assert result.degraded
    assert result.models
    assert all(m.id for m in result.models)


def test_catalog_without_key_never_calls_the_network(tmp_path, monkeypatch):
    catalog = ModelCatalog(str(tmp_path / "cache.json"))

    def explode(*args, **kwargs):
        raise AssertionError("network client must not be constructed without a key")

    monkeypatch.setattr(orcarouter, "OrcaRouterClient", explode)
    result = catalog.load(CHAT, api_key="")
    assert result.source == "verified_fallback"


def test_verified_seed_keeps_ids_and_metadata():
    ids = {m.id for m in orcarouter.VERIFIED_FALLBACK_MODELS}
    assert orcarouter.DEFAULT_MODEL == "orcarouter/auto"
    assert orcarouter.GENERAL_FALLBACK_MODEL == "orcarouter/fusion"
    assert "orca/orcacyber-ultra-1.0" in ids
    assert "orca/orcacyber-zero-1.5" in ids

    gpt = orcarouter.get_model(orcarouter.VERIFIED_FALLBACK_MODELS, "openai/gpt-5.5")
    assert gpt is not None
    assert gpt.reasoning_efforts == ("low", "medium", "high", "xhigh")
    # Unverified modalities are not invented.
    assert gpt.input_modalities == ("text",)

    # No fallback claims image input, so a catalog outage preserves the
    # fail-closed rule for the image-analysis entry point.
    assert orcarouter.fallback_models(MULTIMODAL) == []


def test_seed_defaults_and_cyber_models_are_chat_models():
    ids = [m.id for m in orcarouter.fallback_models(CHAT)]
    assert ids[0] == "orcarouter/auto"
    assert "orcarouter/fusion" in ids
    assert "orca/orcacyber-ultra-1.0" in ids


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def test_selected_model_is_kept_only_when_still_compatible():
    models = filter_models(records(), CHAT)
    assert resolve_selected_model("vendor/text-chat", models) == ("vendor/text-chat", False)
    assert resolve_selected_model("vendor/image-gen", models) == ("orcarouter/auto", True)
    assert resolve_selected_model("", models) == ("orcarouter/auto", False)
    assert resolve_selected_model("vendor/text-chat", []) == ("", True)
