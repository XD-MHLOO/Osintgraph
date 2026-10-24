"""Provider registration, credential and model-selection tests."""

import json

import pytest

from osintgraph import credential_manager as credential_module
from osintgraph.constants import SERVICE_MAP
from osintgraph.credential_manager import DEFAULT_CREDENTIALS, get_credential_manager
from osintgraph.services import llm_analyzer, llm_models, model_picker, orcarouter
from conftest import catalog_payload


def _models():
    return [
        record
        for record in (
            orcarouter.model_from_payload(item) for item in catalog_payload()["data"]
        )
        if record is not None
    ]


@pytest.fixture(autouse=True)
def clean_credentials():
    cm = get_credential_manager()
    cm.reset()
    yield cm
    cm.reset()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_provider_is_a_named_first_class_entry():
    assert SERVICE_MAP["orcarouter"] == ["ORCAROUTER_API_KEY"]
    assert orcarouter.PROVIDER_LABEL == "OrcaRouter Cyber Inference"
    assert orcarouter.PROVIDER_ID == "orcarouter"
    assert orcarouter.DEFAULT_API_BASE == "https://api.orcarouter.ai/v1"
    # Existing providers are untouched.
    assert SERVICE_MAP["gemini"] == ["GEMINI_API_KEY"]


def test_default_model_and_cyber_recommendations():
    assert orcarouter.DEFAULT_MODEL == "orcarouter/auto"
    assert orcarouter.GENERAL_FALLBACK_MODEL == "orcarouter/fusion"
    assert set(orcarouter.CYBER_MODELS) == {
        "orca/orcacyber-ultra-1.0",
        "orca/orcacyber-zero-1.5",
        "orca/orcacyber-zero-1.0",
    }


# ---------------------------------------------------------------------------
# API key lifecycle (the project's existing credential store)
# ---------------------------------------------------------------------------


def test_api_key_set_read_clear_and_mask():
    cm = get_credential_manager()
    key = "sk-orca-abcdefghijklmnop1234"
    cm.set("ORCAROUTER_API_KEY", key)
    assert cm.get("ORCAROUTER_API_KEY") == key
    assert orcarouter.mask_key(key) == "...1234"
    assert key not in orcarouter.mask_key(key)
    assert cm.get("ORCAROUTER_API_KEY") == key  # still readable after masking

    cm.reset(["ORCAROUTER_API_KEY"])
    assert cm.get("ORCAROUTER_API_KEY") == ""
    assert orcarouter.mask_key("") == ""


def test_key_format_hint_is_only_a_hint():
    assert orcarouter.key_format_hint("sk-orca-whatever") is None
    assert "sk-orca-" in orcarouter.key_format_hint("sk-other")


def test_credentials_file_gains_provider_keys_without_losing_data(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"GEMINI_API_KEY": "existing-gemini-key"}))
    monkeypatch.setenv("OSINTGRAPH_CREDENTIALS_FILE", str(path))

    original = credential_module.CredentialManager._instance
    credential_module.CredentialManager._instance = None
    try:
        migrated = credential_module.CredentialManager()
        assert migrated.get("GEMINI_API_KEY") == "existing-gemini-key"
        assert migrated.get("ORCAROUTER_API_KEY") == ""
        assert migrated.get("LLM_PROVIDER") == ""
        assert "ORCAROUTER_MODEL" in migrated.credentials
    finally:
        credential_module.CredentialManager._instance = original


def test_default_credentials_include_provider_entries():
    for key in ("ORCAROUTER_API_KEY", "ORCAROUTER_MODEL", "LLM_PROVIDER"):
        assert key in DEFAULT_CREDENTIALS


# ---------------------------------------------------------------------------
# Provider resolution and transport
# ---------------------------------------------------------------------------


def test_provider_resolution_prefers_explicit_choice_then_key():
    cm = get_credential_manager()
    assert llm_models.get_llm_provider() == "gemini"

    cm.set("ORCAROUTER_API_KEY", "sk-orca-test")
    assert llm_models.get_llm_provider() == "orcarouter"

    cm.set("LLM_PROVIDER", "gemini")
    assert llm_models.get_llm_provider() == "gemini"

    cm.set("LLM_PROVIDER", "orcarouter")
    assert llm_models.get_llm_provider() == "orcarouter"
    assert llm_models.get_selected_model() == "orcarouter/auto"


def test_chat_model_uses_inference_origin_and_bearer_key():
    cm = get_credential_manager()
    cm.set("ORCAROUTER_API_KEY", "sk-orca-test")
    cm.set("ORCAROUTER_MODEL", "orca/orcacyber-ultra-1.0")

    model = llm_models.build_orcarouter_chat_model()
    assert model.model_name == "orca/orcacyber-ultra-1.0"
    assert model.openai_api_base == "https://api.orcarouter.ai/v1"
    assert model.openai_api_key.get_secret_value() == "sk-orca-test"
    assert model.temperature == 0.0


def test_chat_model_honours_explicit_api_override(monkeypatch):
    cm = get_credential_manager()
    cm.set("ORCAROUTER_API_KEY", "sk-orca-test")
    monkeypatch.setenv("ORCAROUTER_API_BASE_URL", "https://api.internal/v1")
    model = llm_models.build_orcarouter_chat_model()
    assert model.openai_api_base == "https://api.internal/v1"


def test_chat_model_is_unavailable_without_a_key():
    cm = get_credential_manager()
    cm.set("LLM_PROVIDER", "orcarouter")
    assert llm_models.get_chat_model("agent") is None
    assert llm_models.has_llm_credentials() is False
    with pytest.raises(orcarouter.OrcaRouterError) as err:
        llm_models.build_orcarouter_chat_model()
    assert err.value.kind == "auth"


def test_llm_credentials_follow_the_active_provider():
    cm = get_credential_manager()
    assert llm_models.has_llm_credentials() is False
    cm.set("GEMINI_API_KEY", "gemini-test-key")
    assert llm_models.has_llm_credentials() is True

    cm.set("ORCAROUTER_API_KEY", "sk-orca-test")
    cm.set("LLM_PROVIDER", "orcarouter")
    assert llm_models.has_llm_credentials() is True

    cm.reset(["ORCAROUTER_API_KEY"])
    assert llm_models.has_llm_credentials() is False


def test_auth_failure_maps_to_a_clear_actionable_message():
    class Rejected(Exception):
        status_code = 401

    hint = llm_analyzer._auth_hint(Rejected("401"))
    assert "osintgraph setup orcarouter" in hint
    assert "sk-orca" not in hint

    class Other(Exception):
        status_code = 500

    assert llm_analyzer._auth_hint(Other("500")) is None


def test_analyzer_requires_a_configured_model():
    cm = get_credential_manager()
    cm.set("LLM_PROVIDER", "orcarouter")
    analyzer = llm_analyzer.LLMAnalyzer(default_model=None, fallback_model=None)
    assert analyzer.default_model is None
    with pytest.raises(orcarouter.OrcaRouterError):
        analyzer._current_model(0, 1)


def test_image_analysis_fails_closed_for_a_text_only_model(monkeypatch):
    from types import SimpleNamespace

    cm = get_credential_manager()
    cm.set("ORCAROUTER_API_KEY", "sk-orca-test")
    cm.set("LLM_PROVIDER", "orcarouter")

    vision = orcarouter.ModelRecord(
        id="vendor/vision-chat",
        endpoint_types=("openai",),
        input_modalities=("text", "image"),
    )
    monkeypatch.setattr(
        llm_models,
        "load_multimodal_catalog",
        lambda refresh=False: orcarouter.CatalogResult(models=[vision], source="live"),
    )

    text_only = SimpleNamespace(model_name="vendor/text-chat")
    analyzer = llm_analyzer.LLMAnalyzer(default_model=text_only, fallback_model=None)
    with pytest.raises(RuntimeError) as err:
        analyzer.analyze_image("https://example.invalid/p.jpg", "system", True)
    assert "does not declare image input" in str(err.value)
    assert "capability multimodal" in str(err.value)

    # The guard accepts a model that the catalog explicitly advertises.
    analyzer._require_multimodal(SimpleNamespace(model_name="vendor/vision-chat"))


# ---------------------------------------------------------------------------
# Model selector options
# ---------------------------------------------------------------------------


def test_chat_selector_options_come_from_the_catalog():
    options = model_picker.build_options(_models(), orcarouter.CHAT)
    ids = [m.id for m in options]
    assert "vendor/text-chat" in ids
    assert "vendor/image-gen" not in ids
    assert "vendor/embed" not in ids


def test_image_attachment_recomputes_the_selector_and_clears_incompatible_value():
    models = _models()
    text_options = model_picker.build_options(models, orcarouter.CHAT)
    assert any(m.id == "vendor/text-chat" for m in text_options)

    vision_options = model_picker.build_options(models, orcarouter.MULTIMODAL)
    vision_ids = [m.id for m in vision_options]
    assert "vendor/text-chat" not in vision_ids
    assert set(vision_ids) == {"vendor/gemini-chat", "vendor/vision-chat"}

    # A text-only selection is not kept once image input is required.
    selected, reset = orcarouter.resolve_selected_model("vendor/text-chat", vision_options)
    assert reset is True
    assert selected in vision_ids


def test_selector_accepts_numbers_ids_and_unique_substrings():
    options = model_picker.build_options(_models(), orcarouter.CHAT)
    assert model_picker.parse_selection("1", options) == options[0].id
    assert model_picker.parse_selection("vendor/text-chat", options) == "vendor/text-chat"
    assert model_picker.parse_selection("vision", options) == "vendor/vision-chat"
    assert model_picker.parse_selection("no-such-model", options) == ""
    assert model_picker.parse_selection("", options, default="orcarouter/auto") == "orcarouter/auto"
    assert model_picker.parse_selection("q", options) is None


def test_selector_never_accepts_free_text_outside_the_catalog():
    options = model_picker.build_options(_models(), orcarouter.CHAT)
    answers = iter(["anything/goes", "anything/goes", "anything/goes"])
    written = []
    picked = model_picker.choose_model(
        options,
        capability=orcarouter.CHAT,
        read=lambda prompt: next(answers),
        write=written.append,
        attempts=3,
    )
    assert picked is None
    assert any("No model matches" in line for line in written)


def test_selector_cancels_on_empty_catalog():
    written = []
    picked = model_picker.choose_model(
        [], capability=orcarouter.MULTIMODAL, write=written.append, read=lambda p: "1"
    )
    assert picked is None
    assert any("Nothing has been changed" in line for line in written)


def test_degraded_catalog_is_labelled_in_the_selector():
    text = model_picker.render(
        orcarouter.fallback_models(orcarouter.CHAT),
        orcarouter.CHAT,
        "verified_fallback",
        degraded=True,
    )
    assert "verified_fallback" in text
    assert "DEGRADED" in text
    assert "orcarouter/auto" in text


# ---------------------------------------------------------------------------
# Regression: the Gemini path still works as before
# ---------------------------------------------------------------------------


def test_gemini_models_are_still_exposed():
    for name in (
        "gemini_2_0_flash",
        "gemini_2_0_flash_with_limit",
        "gemini_2_5_flash_llm_with_limit",
        "text_embedding_004_llm",
    ):
        assert hasattr(llm_models, name)
    # Without any key the agent model stays unavailable, as before this change.
    assert llm_models.get_llm_provider() == "gemini"
    assert llm_models.get_chat_model("agent") is None
