"""Base agent class with centralised LLM configuration resolution."""

from typing import Any, Dict, List, Optional

from crewai import Agent, LLM

from ..config.loader import config_loader, AgentConfig
from ..config.settings import settings
from ..llm_budget import check_and_increment


def _with_budget(llm: Any) -> Any:
    """Wrap an LLM instance so every call checks the per-run budget FIRST.

    crewai.LLM is a factory (__new__ routes to native provider classes), so
    budget enforcement wraps the built instance's call/acall methods. Every
    agent in the app gets a wrapped LLM, so once the budget is exhausted no
    code path — agent loop, retry layer, or framework bug — can reach the
    LLM provider again within the run.
    """
    orig_call = llm.call

    def _budgeted_call(*args, **kwargs):
        check_and_increment()
        return orig_call(*args, **kwargs)

    llm.call = _budgeted_call

    orig_acall = getattr(llm, "acall", None)
    if orig_acall is not None:
        async def _budgeted_acall(*args, **kwargs):
            check_and_increment()
            return await orig_acall(*args, **kwargs)

        llm.acall = _budgeted_acall
    return llm


def preflight_llm_credentials(provider_override: Optional[str] = None) -> List[str]:
    """Return human-readable problems (empty list = OK) for the run's providers.

    Resolves every LLM provider the run could use — CLI override, else the env
    global, else the llm_config global plus any per-agent provider overrides —
    and checks each has its API key set. Lets a misconfigured run fail in ~1s
    with a clear message instead of after a full data-collection pass.
    """
    llm_cfg = config_loader.load_llm_config()
    providers = set()
    if provider_override:
        providers.add(provider_override)  # CLI override applies to every agent
    else:
        providers.add(settings.llm_provider or llm_cfg.global_defaults.provider)
        # Per-agent provider overrides still take effect under an env global
        for agent_cfg in llm_cfg.agents.values():
            if isinstance(agent_cfg, dict) and agent_cfg.get("provider"):
                providers.add(agent_cfg["provider"])

    problems: List[str] = []
    for p in sorted(providers):
        if p == "openai" and not settings.openai_api_key:
            problems.append("provider 'openai' is selected but OPENAI_API_KEY is not set")
        elif p == "anthropic" and not settings.anthropic_api_key:
            problems.append("provider 'anthropic' is selected but ANTHROPIC_API_KEY is not set")
        # ollama and other local/keyless providers need no key
    return problems


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
        # LLM, tools, and Agent are built lazily on first get_agent() call
        # so the app can be constructed without an API key (e.g. for --help).
        self._llm: Optional[Any] = None
        self._tools: Optional[List[Any]] = None
        self._agent: Optional[Any] = None

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
            "timeout": g.timeout,
            "max_retries": g.max_retries,
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
        for key in ("provider", "model", "temperature", "max_tokens", "timeout", "max_retries"):
            if agent_yaml.get(key) is not None:
                resolved[key] = agent_yaml[key]

        # 4. Apply agents.yaml llm_config block (provider/model/temperature/max_tokens)
        agent_block = self.config.llm_config or {}
        for key in ("provider", "model", "temperature", "max_tokens", "timeout", "max_retries"):
            if agent_block.get(key) is not None:
                resolved[key] = agent_block[key]

        # 5. Apply constructor args (highest priority)
        if self._init_provider is not None:
            resolved["provider"] = self._init_provider
        if self._init_model is not None:
            resolved["model"] = self._init_model

        return resolved

    # OpenAI models that require max_completion_tokens instead of max_tokens
    _COMPLETION_TOKENS_PREFIXES = ("o1", "o3", "o4-", "gpt-5")

    def _uses_completion_tokens(self, model: str) -> bool:
        """Return True for OpenAI models that only accept max_completion_tokens."""
        m = model.lower()
        if "/" in m:
            m = m.split("/", 1)[1]
        return any(m.startswith(p) for p in self._COMPLETION_TOKENS_PREFIXES)

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

        # Newer OpenAI models (o1, o3, gpt-5, …) only accept max_completion_tokens.
        # The crewai native OpenAI class branches on which parameter is set.
        token_kwargs: dict = (
            {"max_completion_tokens": self._resolved["max_tokens"]}
            if provider == "openai" and self._uses_completion_tokens(model)
            else {"max_tokens": self._resolved["max_tokens"]}
        )

        return _with_budget(LLM(
            model=litellm_model,
            temperature=self._resolved["temperature"],
            **token_kwargs,
            timeout=self._resolved["timeout"],
            max_retries=self._resolved["max_retries"],
            api_key=settings.openai_api_key if provider == "openai"
                    else settings.anthropic_api_key if provider == "anthropic"
                    else None,
        ))

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
            tools=self._tools or [],
            llm=self._llm,
            max_iter=self.config.max_iter,
            # Hard timeout so a hung LLM/tool call can never stall a run forever
            max_execution_time=self.config.max_execution_time,
            # RPM throttle: a runaway loop is slowed to a crawl long before
            # the timeout or call budget end it
            max_rpm=self.config.max_rpm,
            # One retry after execution errors — retry storms multiply cost
            max_retry_limit=self.config.max_retry_limit,
            # Current date in task context (correct 'as of' statements for free)
            inject_date=self.config.inject_date,
            # CrewAI-native tool-result cache: identical tool calls within a run
            # return the cached result, which also lets CrewAI's repeated-call
            # guard terminate tool loops
            cache=True,
            respect_context_window=True,
        )
        # reasoning is opt-in via agents.yaml llm_config block
        agent_block = self.config.llm_config or {}
        if agent_block.get("reasoning"):
            kwargs["reasoning"] = True
            kwargs["max_reasoning_attempts"] = agent_block.get("max_reasoning_attempts", 3)
        return Agent(**kwargs)

    # ── Public helpers ────────────────────────────────────────────────────────

    def get_agent(self) -> Agent:
        if self._agent is None:
            if self._llm is None:
                self._llm = self._build_llm()
            if self._tools is None:
                self._tools = self._get_tools()
            self._agent = self._create_agent()
        return self._agent

    def get_config(self) -> AgentConfig:
        return self.config

    def get_resolved_llm_config(self) -> Dict[str, Any]:
        """Expose the resolved LLM config (useful for debugging/logging)."""
        return dict(self._resolved)
