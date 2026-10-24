"""Live smoke test: real catalog and one real inference call.

Runs only when the verifier supplies ORCAROUTER_API_KEY. Everything goes
through the provider code paths added in this change (credential store ->
model catalog -> LangChain OpenAI-compatible client), never through a
standalone HTTP call.
"""

import os

import pytest
from langchain_core.messages import HumanMessage

from osintgraph.credential_manager import get_credential_manager
from osintgraph.services import llm_models, orcarouter


def _live_key(request):
    key = getattr(request.config, "_osintgraph_live_key", "")
    return key or os.environ.get("ORCAROUTER_API_KEY", "")


@pytest.fixture()
def configured(request):
    key = _live_key(request)
    if not key:
        pytest.skip("ORCAROUTER_API_KEY not provided")
    cm = get_credential_manager()
    cm.set("ORCAROUTER_API_KEY", key)
    cm.set("LLM_PROVIDER", "orcarouter")
    yield cm
    cm.reset()


def test_live_catalog_through_provider(configured):
    result = llm_models.load_chat_catalog(refresh=True)
    assert result.source == "live", result.error
    ids = [model.id for model in result.models]
    assert ids, "the live catalog returned no chat models"
    assert orcarouter.DEFAULT_MODEL in ids

    multimodal = llm_models.load_multimodal_catalog(refresh=True)
    assert multimodal.source == "live", multimodal.error
    # Every option offered for the image-analysis entry declares image input.
    assert all("image" in model.input_modalities for model in multimodal.models)
    assert all(model.id in ids for model in multimodal.models)


def test_live_inference_through_provider(configured):
    result = llm_models.load_chat_catalog(refresh=True)
    assert result.source == "live", result.error

    by_id = {model.id: model for model in result.models}
    preferred = [model_id for model_id in orcarouter.CYBER_MODELS if model_id in by_id]
    preferred += [
        model_id
        for model_id in by_id
        if model_id not in preferred
        and model_id not in (orcarouter.DEFAULT_MODEL, orcarouter.GENERAL_FALLBACK_MODEL)
    ]

    failure = None
    for model_id in preferred[:3]:
        configured.set("ORCAROUTER_MODEL", model_id)
        model = llm_models.get_chat_model("agent")
        assert model is not None
        assert model.openai_api_base == orcarouter.resolve_api_base()
        try:
            response = model.invoke(
                [HumanMessage(content="Reply with the single word OK.")], timeout=45
            )
        except Exception as exc:  # availability varies per workspace/tier
            failure = "{}: {}".format(type(exc).__name__, str(exc)[:200])
            continue
        content = response.content
        if isinstance(content, list):
            content = " ".join(part.get("text", "") for part in content if isinstance(part, dict))
        assert isinstance(content, str) and content.strip()
        return
    pytest.fail("no catalog chat model answered a live request: {}".format(failure))
