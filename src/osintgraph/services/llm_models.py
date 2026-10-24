from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

import logging
import os

from ..credential_manager import get_credential_manager
from ..constants import MODEL_CATALOG_CACHE_FILE
from . import orcarouter

cm = get_credential_manager()
logger = logging.getLogger(__name__)

rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.16,
    check_every_n_seconds=0.5,
    max_bucket_size=5,
)

if cm.get("GEMINI_API_KEY"):

    gemini_2_0_flash = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=cm.get("GEMINI_API_KEY"),
        temperature=0.0,
    )

    gemini_2_0_flash_with_limit = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=cm.get("GEMINI_API_KEY"),
        temperature=0.0,
        rate_limiter=rate_limiter
    )

    gemini_2_5_flash_lite_llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite-preview-06-17",
        google_api_key=cm.get("GEMINI_API_KEY"),
        temperature=0.0,
    )

    gemini_2_5_flash_lite_llm_with_limit = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite-preview-06-17",
        google_api_key=cm.get("GEMINI_API_KEY"),
        temperature=0.0,
        rate_limiter=rate_limiter
    )

    gemini_2_5_flash_llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=cm.get("GEMINI_API_KEY"),
        temperature=0.0,
    )

    gemini_2_5_flash_llm_with_limit = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=cm.get("GEMINI_API_KEY"),
        temperature=0.0,
        rate_limiter=rate_limiter
    )


    text_embedding_004_llm = GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004",
        google_api_key=cm.get("GEMINI_API_KEY")
    )

else:
    gemini_2_0_flash = None
    gemini_2_0_flash_with_limit = None
    gemini_2_5_flash_lite_llm = None
    gemini_2_5_flash_lite_llm_with_limit = None
    gemini_2_5_flash_llm = None
    gemini_2_5_flash_llm_with_limit = None
    text_embedding_004_llm = None


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------
#
# Osintgraph historically ships one provider (Gemini). OrcaRouter Cyber
# Inference is a named, first-class alternative: choosing it changes where
# requests go, not how the rest of the application calls them. Every AI entry
# point resolves its model through the helpers below, so both providers share
# one routing seam.

_GEMINI_ROLE_MODELS = {
    "agent": "gemini_2_0_flash",
    "agent_limited": "gemini_2_0_flash_with_limit",
    "analyzer": "gemini_2_0_flash_with_limit",
    "analyzer_fallback": "gemini_2_5_flash_llm_with_limit",
    "template": "gemini_2_5_flash_llm_with_limit",
}


def get_orcarouter_api_key():
    """Return the user's OrcaRouter key from the project's credential store.

    Falling back to ``ORCAROUTER_API_KEY`` keeps CI and live smoke tests able to
    exercise the same code path without writing a credential file.
    """
    key = orcarouter.normalize_api_key(cm.get("ORCAROUTER_API_KEY"))
    if key:
        return key
    return orcarouter.normalize_api_key(os.environ.get("ORCAROUTER_API_KEY", ""))


def get_llm_provider():
    """Resolve the active provider: ``orcarouter`` or ``gemini``."""
    explicit = (cm.get("LLM_PROVIDER") or "").strip().lower()
    if explicit in ("orcarouter", "gemini"):
        return explicit
    if get_orcarouter_api_key():
        return orcarouter.PROVIDER_ID
    return "gemini"


def get_selected_model():
    """The OrcaRouter model chosen during setup (default ``orcarouter/auto``)."""
    return (
        (cm.get("ORCAROUTER_MODEL") or "").strip()
        or orcarouter.DEFAULT_MODEL
    )


def has_llm_credentials():
    """True when the active provider has a usable credential."""
    if get_llm_provider() == orcarouter.PROVIDER_ID:
        return bool(get_orcarouter_api_key())
    return bool(cm.get("GEMINI_API_KEY"))


def build_orcarouter_chat_model(model_id=None, temperature=0.0, timeout=120):
    """Build the OpenAI-compatible LangChain chat client for OrcaRouter.

    Imported lazily so the catalog/credential modules stay usable without the
    LangChain stack (tests, setup wizard).
    """
    from langchain_openai import ChatOpenAI

    api_key = get_orcarouter_api_key()
    if not api_key:
        raise orcarouter.OrcaRouterError(
            "No OrcaRouter API key is configured. Run `osintgraph setup orcarouter`.",
            kind="auth",
        )
    return ChatOpenAI(
        model=model_id or get_selected_model(),
        base_url=orcarouter.resolve_api_base(),
        api_key=api_key,
        temperature=temperature,
        timeout=timeout,
        max_retries=2,
    )


def get_chat_model(role="analyzer"):
    """Provider-aware chat model factory.

    Returns ``None`` when the active provider has no usable credential, which
    matches the historical Gemini behaviour callers already handle.
    """
    if get_llm_provider() == orcarouter.PROVIDER_ID:
        if not get_orcarouter_api_key():
            return None
        return build_orcarouter_chat_model()

    name = _GEMINI_ROLE_MODELS.get(role, "gemini_2_0_flash_with_limit")
    return globals().get(name)


def get_orcarouter_fallback_model():
    """Second model used when the decoded output keeps failing."""
    if get_llm_provider() != orcarouter.PROVIDER_ID or not get_orcarouter_api_key():
        return None
    return build_orcarouter_chat_model(orcarouter.GENERAL_FALLBACK_MODEL)


# ---------------------------------------------------------------------------
# Model catalog
# ---------------------------------------------------------------------------

_model_catalog = None


def get_model_catalog():
    global _model_catalog
    if _model_catalog is None:
        _model_catalog = orcarouter.ModelCatalog(MODEL_CATALOG_CACHE_FILE)
    return _model_catalog


def load_chat_catalog(refresh=False):
    """Live, capability-filtered chat catalog plus its provenance."""
    return get_model_catalog().load(
        orcarouter.CHAT, api_key=get_orcarouter_api_key(), refresh=refresh
    )


def load_multimodal_catalog(refresh=False):
    """Chat models that explicitly accept image input (fail closed otherwise)."""
    return get_model_catalog().load(
        orcarouter.MULTIMODAL, api_key=get_orcarouter_api_key(), refresh=refresh
    )


def load_embedding_catalog(refresh=False):
    return get_model_catalog().load(
        orcarouter.EMBEDDING, api_key=get_orcarouter_api_key(), refresh=refresh
    )


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


def get_embeddings_model():
    """Provider-aware embeddings client.

    OrcaRouter is used only when its catalog advertises an embedding-capable
    model for this workspace. The Neo4j vector indexes in this project are
    created at 768 dimensions, so an incompatible OrcaRouter embedding model
    would corrupt search; in that case the existing Gemini embeddings are kept
    and the reason is logged instead of silently mixing providers.
    """
    if get_llm_provider() == orcarouter.PROVIDER_ID and get_orcarouter_api_key():
        result = load_embedding_catalog()
        selected = (cm.get("ORCAROUTER_EMBEDDING_MODEL") or "").strip()
        model_id = ""
        if selected and orcarouter.get_model(result.models, selected):
            model_id = selected
        elif result.models:
            model_id = result.models[0].id
        if model_id:
            from langchain_openai import OpenAIEmbeddings
            return OpenAIEmbeddings(
                model=model_id,
                base_url=orcarouter.resolve_api_base(),
                api_key=get_orcarouter_api_key(),
                check_embedding_ctx_length=False,
            )
        logger.warning(
            "OrcaRouter advertises no embedding models for this workspace; "
            "semantic search keeps using Gemini embeddings when configured."
        )
    if text_embedding_004_llm is None:
        logger.warning(
            "No embeddings provider is configured. Graph vector indexing and "
            "semantic search are unavailable."
        )
    return text_embedding_004_llm
