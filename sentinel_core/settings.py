"""
Deployment Settings

All environment-specific configuration in one place, read from environment
variables so the same image runs in demo and production without code changes.

The `deployment_mode` switch is the important one. In `demo` the platform is
self-contained: it generates its own traffic, exposes chaos-injection
endpoints, and simulates pull requests. In `production` those are off by
default and the platform only consumes real telemetry and opens real PRs.
Shipping a demo default that quietly stays on in production is how a
fault-injection endpoint ends up reachable from the internet.
"""
from __future__ import annotations

import os
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class DeploymentMode(str, Enum):
    DEMO = "demo"
    PRODUCTION = "production"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


class GitHubSettings(BaseModel):
    """Configuration for real pull request creation."""

    enabled: bool = False
    token: Optional[str] = None
    repository: Optional[str] = Field(default=None, description="owner/name")
    base_branch: str = "main"
    api_url: str = "https://api.github.com"

    @property
    def is_configured(self) -> bool:
        return bool(self.enabled and self.token and self.repository)

    def validation_errors(self) -> List[str]:
        """Explain exactly what is missing, rather than failing at call time."""
        if not self.enabled:
            return []
        problems = []
        if not self.token:
            problems.append("SENTINEL_GITHUB_TOKEN is not set")
        if not self.repository:
            problems.append("SENTINEL_GITHUB_REPOSITORY is not set (expected 'owner/name')")
        elif "/" not in self.repository:
            problems.append(f"SENTINEL_GITHUB_REPOSITORY must be 'owner/name', got {self.repository!r}")
        return problems


class LLMSettings(BaseModel):
    """
    Configuration for model-backed root-cause analysis.

    Enabled by default: an API key present in the environment is taken as
    intent to use it. Set SENTINEL_LLM_ENABLED=false to force the
    deterministic path (useful in CI, or to run the demo without spend).
    """

    enabled: bool = True
    api_key: Optional[str] = None
    model: str = "claude-opus-5"
    effort: str = "high"
    max_tokens: int = 8000

    @property
    def is_configured(self) -> bool:
        return bool(self.enabled and self.api_key)


class Settings(BaseModel):
    """Process-wide deployment configuration."""

    deployment_mode: DeploymentMode = DeploymentMode.DEMO

    log_level: str = "INFO"

    # HTTP surface
    cors_allow_origins: List[str] = Field(default_factory=lambda: ["*"])
    api_key: Optional[str] = Field(
        default=None,
        description="When set, every /api route requires a matching X-API-Key header",
    )

    # Demo-only surfaces
    enable_traffic_generator: bool = True
    enable_chaos_endpoints: bool = True

    # Continuous ingestion. 0 disables the background poller, leaving ingestion
    # manual via POST /api/ingestion/run.
    ingestion_poll_seconds: int = 0

    github: GitHubSettings = Field(default_factory=GitHubSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)

    @classmethod
    def from_env(cls) -> "Settings":
        mode_raw = os.getenv("SENTINEL_DEPLOYMENT_MODE", "demo").strip().lower()
        mode = DeploymentMode(mode_raw) if mode_raw in {m.value for m in DeploymentMode} else DeploymentMode.DEMO
        is_prod = mode is DeploymentMode.PRODUCTION

        return cls(
            deployment_mode=mode,
            log_level=os.getenv("SENTINEL_LOG_LEVEL", "INFO").strip().upper(),
            # A wildcard CORS default is acceptable for a local demo and is not
            # acceptable in production, so the default flips with the mode.
            cors_allow_origins=_env_list(
                "SENTINEL_CORS_ORIGINS", [] if is_prod else ["*"]
            ),
            api_key=os.getenv("SENTINEL_API_KEY") or None,
            # Synthetic traffic and fault injection are demo scaffolding. They
            # default off in production so a misconfigured deploy fails closed.
            enable_traffic_generator=_env_bool(
                "SENTINEL_ENABLE_TRAFFIC_GENERATOR", not is_prod
            ),
            enable_chaos_endpoints=_env_bool(
                "SENTINEL_ENABLE_CHAOS_ENDPOINTS", not is_prod
            ),
            ingestion_poll_seconds=_env_int(
                "SENTINEL_INGESTION_POLL_SECONDS", 30 if is_prod else 0
            ),
            llm=LLMSettings(
                enabled=_env_bool("SENTINEL_LLM_ENABLED", True),
                # Accept the SDK's standard variable so an already-configured
                # environment works without a Sentinel-specific rename.
                api_key=(
                    os.getenv("SENTINEL_ANTHROPIC_API_KEY")
                    or os.getenv("ANTHROPIC_API_KEY")
                    or None
                ),
                model=os.getenv("SENTINEL_LLM_MODEL", "claude-opus-5"),
                effort=os.getenv("SENTINEL_LLM_EFFORT", "high"),
                max_tokens=_env_int("SENTINEL_LLM_MAX_TOKENS", 8000),
            ),
            github=GitHubSettings(
                enabled=_env_bool("SENTINEL_GITHUB_ENABLED", is_prod),
                token=os.getenv("SENTINEL_GITHUB_TOKEN") or None,
                repository=os.getenv("SENTINEL_GITHUB_REPOSITORY") or None,
                base_branch=os.getenv("SENTINEL_GITHUB_BASE_BRANCH", "main"),
                api_url=os.getenv("SENTINEL_GITHUB_API_URL", "https://api.github.com"),
            ),
        )

    @property
    def is_production(self) -> bool:
        return self.deployment_mode is DeploymentMode.PRODUCTION

    def startup_warnings(self) -> List[str]:
        """
        Misconfigurations worth shouting about at boot.

        Surfaced in logs and on /api/health so a bad deploy is visible
        immediately rather than at the moment an incident fires.
        """
        warnings: List[str] = []

        if self.is_production:
            if "*" in self.cors_allow_origins:
                warnings.append(
                    "CORS is set to '*' in production. Set SENTINEL_CORS_ORIGINS "
                    "to your dashboard origin."
                )
            if not self.api_key:
                warnings.append(
                    "No SENTINEL_API_KEY set: the API is unauthenticated. Set one, "
                    "or ensure the service is only reachable behind an authenticating proxy."
                )
            if self.enable_chaos_endpoints:
                warnings.append(
                    "Chaos injection endpoints are ENABLED in production. These mutate "
                    "live retrieval configuration; disable unless you are running a "
                    "deliberate game day."
                )
            if self.enable_traffic_generator:
                warnings.append(
                    "The synthetic traffic generator is ENABLED in production. It will "
                    "pollute real telemetry with simulated requests."
                )
            if not self.github.enabled:
                warnings.append(
                    "GitHub integration is disabled: pull requests will be simulated, not opened."
                )
            if not self.llm.is_configured:
                warnings.append(
                    "No Anthropic API key configured: root-cause analysis will fall back to "
                    "the deterministic rule set instead of model-backed investigation."
                )

        warnings.extend(self.github.validation_errors())
        return warnings


settings = Settings.from_env()


def reload_settings() -> Settings:
    """Re-read environment variables. Used by tests."""
    global settings
    settings = Settings.from_env()
    return settings
