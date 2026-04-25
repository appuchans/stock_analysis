"""Base agent class with centralised LLM configuration resolution."""

from typing import Any, Dict, List, Optional

from crewai import Agent, LLM

from ..config.loader import config_loader, AgentConfig
from ..config.settings import settings


class BaseAgent:
    """Base agent that resolves LLM provider/model from a multi-layer config chain.

    Priority (highest wins):
      constructor args  >  agents.yaml llm_config  >  llm_config.yaml per-agent
      >  env vars (settings)  >  llm_config.yaml global defaults
    """

    def __init__(
        self,
        agent_name: str,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.agent_name = agent_name
        self._init_provider = llm_provider  # may be None → use config
        self._init_model = model            # may be None → use config
        self.config = config_loader.get_agent_config(agent_name)
        self._resolved = self._resolve_llm_config()
        self.llm = self._build_llm()
        self.tools = self._get_tools()
        self.agent = self._create_agent()

    # ── LLM resolution ────────────────────────────────────────────────────────

    def _resolve_llm_config(self) -> Dict[str, Any]:
        """Merge all config sources into a single resolved dict.

        Resolution order (lowest → highest priority):
          1. llm_config.yaml global defaults
          2. env vars via settings (global deployment override)
          3. llm_config.yaml per-agent overrides
          4. agents.yaml llm_config block (per-agent fine-grained)
          5. constructor args (programmatic override)
        """
        llm_file_cfg = config_loader.load_llm_config()
        g = llm_file_cfg.global_defaults

        # 1. Start with yaml global defaults
        resolved: Dict[str, Any] = {
            "provider": g.provider,
            "model": g.model,
            "temperature": g.temperature,
            "max_tokens": g.max_tokens,
        }

        # 2. Apply settings (env vars) — only when non-empty
        if settings.llm_provider:
            resolved["provider"] = settings.llm_provider
        if settings.llm_model:
            resolved["model"] = settings.llm_model
        # temperature / max_tokens from settings always apply (they have numeric defaults)
        resolved["temperature"] = settings.temperature
        resolved["max_tokens"] = settings.max_tokens

        # 3. Apply llm_config.yaml per-agent overrides
        agent_yaml = llm_file_cfg.agents.get(self.agent_name) or {}
        for key in ("provider", "model", "temperature", "max_tokens"):
            if agent_yaml.get(key) is not None:
                resolved[key] = agent_yaml[key]

        # 4. Apply agents.yaml llm_config block (provider/model/temperature/max_tokens)
        agent_block = self.config.llm_config or {}
        for key in ("provider", "model", "temperature", "max_tokens"):
            if agent_block.get(key) is not None:
                resolved[key] = agent_block[key]

        # 5. Apply constructor args (highest priority)
        if self._init_provider is not None:
            resolved["provider"] = self._init_provider
        if self._init_model is not None:
            resolved["model"] = self._init_model

        return resolved

    def _build_llm(self) -> LLM:
        """Construct a crewai.LLM from the resolved config."""
        provider = self._resolved["provider"]
        model = self._resolved["model"]

        # Validate API key before attempting to construct the LLM
        if provider == "openai" and not settings.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. "
                "Set it in .env or as an environment variable."
            )
        if provider == "anthropic" and not settings.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. "
                "Set it in .env or as an environment variable."
            )

        # Build the LiteLLM model string: "<prefix><model>"
        llm_cfg = config_loader.load_llm_config()
        prefix = llm_cfg.provider_prefixes.get(provider, f"{provider}/")
        # Avoid double-prefixing if caller already included the prefix
        if "/" in model:
            litellm_model = model
        else:
            litellm_model = f"{prefix}{model}"

        return LLM(
            model=litellm_model,
            temperature=self._resolved["temperature"],
            max_tokens=self._resolved["max_tokens"],
            api_key=settings.openai_api_key if provider == "openai"
                    else settings.anthropic_api_key if provider == "anthropic"
                    else None,
        )

    # ── Agent creation ────────────────────────────────────────────────────────

    def _get_tools(self) -> List[Any]:
        """Return tools for this agent. Override in subclasses."""
        return []

    def _create_agent(self) -> Agent:
        """Instantiate the CrewAI Agent from config + resolved LLM."""
        kwargs: Dict[str, Any] = dict(
            role=self.config.role,
            goal=self.config.goal,
            backstory=self.config.backstory,
            verbose=self.config.verbose,
            allow_delegation=self.config.allow_delegation,
            tools=self.tools,
            llm=self.llm,
            max_iter=self.config.max_iter,
        )
        # reasoning is opt-in via agents.yaml llm_config block
        agent_block = self.config.llm_config or {}
        if agent_block.get("reasoning"):
            kwargs["reasoning"] = True
            kwargs["max_reasoning_attempts"] = agent_block.get("max_reasoning_attempts", 3)
        return Agent(**kwargs)

    # ── Public helpers ────────────────────────────────────────────────────────

    def get_agent(self) -> Agent:
        return self.agent

    def get_config(self) -> AgentConfig:
        return self.config

    def get_resolved_llm_config(self) -> Dict[str, Any]:
        """Expose the resolved LLM config (useful for debugging/logging)."""
        return dict(self._resolved)
