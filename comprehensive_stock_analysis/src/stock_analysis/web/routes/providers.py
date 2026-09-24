"""Provider health/configuration status and LLM selection metadata."""

from typing import Any, Dict

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["providers"])


@router.get("/providers/status")
def providers_status() -> Dict[str, Any]:
    from ...tools.providers import ROUTER

    return ROUTER.status()


@router.get("/llm/options")
def llm_options() -> Dict[str, Any]:
    """Return selectable LLM providers and useful model suggestions."""
    from ...config.loader import config_loader
    from ...config.settings import settings

    llm_config = config_loader.load_llm_config()
    default_provider = settings.llm_provider or llm_config.global_defaults.provider
    default_model = settings.llm_model or llm_config.global_defaults.model
    suggestions = {
        "openai": ["gpt-4o-mini", "gpt-4o", "gpt-5.6-luna", "gpt-5.6-terra"],
        "anthropic": [
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-6",
            "claude-opus-4-6",
        ],
        "ollama": ["llama3.1", "qwen2.5", "deepseek-r1"],
        "gemini": ["gemini/gemini-2.5-flash", "gemini/gemini-2.5-pro"],
        "groq": ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"],
        "openrouter": [
            "z-ai/glm-4.5-air:free",
            "openai/gpt-4o",
            "anthropic/claude-sonnet-4",
        ],
        "zai": ["glm-4.5-flash", "glm-4.7"],
    }
    providers = []
    for provider in sorted(llm_config.provider_prefixes):
        models = list(suggestions.get(provider, []))
        if provider == default_provider and default_model not in models:
            models.insert(0, default_model)
        providers.append({"id": provider, "label": provider.title(), "models": models})
    return {
        "default_provider": default_provider,
        "default_model": default_model,
        "providers": providers,
    }
