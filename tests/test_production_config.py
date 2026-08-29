"""
Production Deployment Tests

Covers the seams that separate a demo run from a real deployment: settings
resolution, the API-key gate, demo-surface gating, and the real GitHub client's
request sequence.
"""
import base64
import json

import pytest
from starlette.testclient import TestClient

from sentinel_core.integrations.github_client import (
    GitHubError,
    RestGitHubClient,
    SimulatedGitHubClient,
    build_github_client,
)
from sentinel_core.settings import DeploymentMode, Settings


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

def _settings(monkeypatch, **env) -> Settings:
    for key in list(env):
        monkeypatch.setenv(key, env[key])
    return Settings.from_env()


def test_demo_mode_is_the_default(monkeypatch):
    monkeypatch.delenv("SENTINEL_DEPLOYMENT_MODE", raising=False)
    s = Settings.from_env()
    assert s.deployment_mode is DeploymentMode.DEMO
    assert s.enable_traffic_generator is True
    assert s.enable_chaos_endpoints is True


def test_production_mode_disables_demo_scaffolding_by_default(monkeypatch):
    """
    The safety-critical default.

    Synthetic traffic pollutes real telemetry and chaos endpoints mutate live
    retrieval config. Both must be off unless explicitly re-enabled.
    """
    s = _settings(monkeypatch, SENTINEL_DEPLOYMENT_MODE="production")
    assert s.enable_traffic_generator is False
    assert s.enable_chaos_endpoints is False


def test_production_defaults_to_deny_all_cors(monkeypatch):
    monkeypatch.delenv("SENTINEL_CORS_ORIGINS", raising=False)
    s = _settings(monkeypatch, SENTINEL_DEPLOYMENT_MODE="production")
    assert s.cors_allow_origins == [], "production must not default to wildcard CORS"


def test_production_enables_continuous_ingestion_by_default(monkeypatch):
    monkeypatch.delenv("SENTINEL_INGESTION_POLL_SECONDS", raising=False)
    s = _settings(monkeypatch, SENTINEL_DEPLOYMENT_MODE="production")
    assert s.ingestion_poll_seconds == 30


def test_unknown_deployment_mode_falls_back_to_demo(monkeypatch):
    """An unrecognised mode must not crash the process at import time."""
    s = _settings(monkeypatch, SENTINEL_DEPLOYMENT_MODE="staging-ish")
    assert s.deployment_mode is DeploymentMode.DEMO


def test_misconfigured_production_reports_every_problem(monkeypatch):
    s = _settings(
        monkeypatch,
        SENTINEL_DEPLOYMENT_MODE="production",
        SENTINEL_CORS_ORIGINS="*",
        SENTINEL_ENABLE_CHAOS_ENDPOINTS="true",
        SENTINEL_ENABLE_TRAFFIC_GENERATOR="true",
    )
    monkeypatch.delenv("SENTINEL_API_KEY", raising=False)
    s = Settings.from_env()
    warnings = " ".join(s.startup_warnings())

    assert "CORS" in warnings
    assert "SENTINEL_API_KEY" in warnings
    assert "Chaos" in warnings
    assert "traffic generator" in warnings


def test_partial_github_config_explains_what_is_missing(monkeypatch):
    s = _settings(
        monkeypatch,
        SENTINEL_GITHUB_ENABLED="true",
        SENTINEL_GITHUB_REPOSITORY="not-a-repo-path",
    )
    monkeypatch.delenv("SENTINEL_GITHUB_TOKEN", raising=False)
    s = Settings.from_env()

    assert not s.github.is_configured
    problems = " ".join(s.github.validation_errors())
    assert "SENTINEL_GITHUB_TOKEN" in problems
    assert "owner/name" in problems


def test_env_bool_accepts_common_spellings(monkeypatch):
    for truthy in ("1", "true", "TRUE", "yes", "on"):
        s = _settings(monkeypatch, SENTINEL_ENABLE_CHAOS_ENDPOINTS=truthy)
        assert s.enable_chaos_endpoints is True, truthy
    for falsy in ("0", "false", "no", "off"):
        s = _settings(monkeypatch, SENTINEL_ENABLE_CHAOS_ENDPOINTS=falsy)
        assert s.enable_chaos_endpoints is False, falsy


# --------------------------------------------------------------------------
# GitHub client selection
# --------------------------------------------------------------------------

def test_unconfigured_github_degrades_to_simulated(monkeypatch):
    """
    A partial config must not crash the incident pipeline mid-remediation.

    Losing the completed investigation because a token was missing is worse
    than delivering a clearly-labelled simulated PR.
    """
    monkeypatch.delenv("SENTINEL_GITHUB_TOKEN", raising=False)
    s = _settings(monkeypatch, SENTINEL_GITHUB_ENABLED="true")
    client = build_github_client(Settings.from_env())
    assert isinstance(client, SimulatedGitHubClient)


def test_fully_configured_github_selects_the_rest_client(monkeypatch):
    s = _settings(
        monkeypatch,
        SENTINEL_GITHUB_ENABLED="true",
        SENTINEL_GITHUB_TOKEN="ghp_example",
        SENTINEL_GITHUB_REPOSITORY="acme/ai-platform",
    )
    client = build_github_client(s)
    assert isinstance(client, RestGitHubClient)
    assert client.repository == "acme/ai-platform"


def test_rest_client_rejects_a_malformed_repository():
    with pytest.raises(ValueError, match="owner/name"):
        RestGitHubClient(token="t", repository="no-slash-here")


def test_simulated_client_marks_its_output_as_simulated():
    ref = SimulatedGitHubClient().open_pull_request(
        branch="fix/x", title="t", body="b", commit_message="c",
        file_changes={"a.py": "content"},
    )
    assert ref.simulated is True


def test_client_interface_exposes_no_merge_method():
    """
    The safety covenant is enforced by absence, not convention.

    If no client can merge, no agent can merge by calling a different method.
    """
    for client in (SimulatedGitHubClient(), RestGitHubClient("t", "o/r")):
        assert not hasattr(client, "merge_pull_request")
        assert not hasattr(client, "merge")


# --------------------------------------------------------------------------
# Real GitHub request sequence
# --------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text
        self.content = b"x" if payload is not None else b""

    def json(self):
        return self._payload


def test_rest_client_performs_the_full_pr_sequence(monkeypatch):
    """resolve base -> create branch -> commit file -> open PR."""
    calls = []

    def fake_request(method, url, headers=None, json=None, timeout=None):
        calls.append((method, url, json))
        if method == "GET" and "/git/ref/heads/main" in url:
            return _FakeResponse(200, {"object": {"sha": "base-sha-abc"}})
        if method == "POST" and url.endswith("/git/refs"):
            return _FakeResponse(201, {"ref": "refs/heads/fix/inc-1"})
        if method == "GET" and "/contents/" in url:
            return _FakeResponse(200, {"sha": "existing-blob-sha"})
        if method == "PUT" and "/contents/" in url:
            return _FakeResponse(200, {"commit": {"sha": "new-commit"}})
        if method == "POST" and url.endswith("/pulls"):
            return _FakeResponse(201, {
                "number": 42,
                "html_url": "https://github.com/acme/ai-platform/pull/42",
            })
        raise AssertionError(f"unexpected call: {method} {url}")

    import httpx
    monkeypatch.setattr(httpx, "request", fake_request)

    client = RestGitHubClient(token="ghp_x", repository="acme/ai-platform")
    ref = client.open_pull_request(
        branch="fix/inc-1",
        title="Fix INC-1",
        body="body",
        commit_message="fix: inc-1",
        file_changes={"rag_service/config.py": "top_k = 8\n"},
    )

    assert ref.number == 42
    assert ref.simulated is False
    assert ref.url.endswith("/pull/42")

    methods = [c[0] for c in calls]
    assert methods == ["GET", "POST", "GET", "PUT", "POST"]

    # The PR must target the configured base branch, not the working branch.
    pr_payload = calls[-1][2]
    assert pr_payload["base"] == "main"
    assert pr_payload["head"] == "fix/inc-1"

    # File content must be base64-encoded, and carry the blob sha for an update.
    put_payload = calls[3][2]
    assert base64.b64decode(put_payload["content"]).decode() == "top_k = 8\n"
    assert put_payload["sha"] == "existing-blob-sha"
    assert put_payload["branch"] == "fix/inc-1"


def test_rest_client_reuses_an_existing_branch(monkeypatch):
    """A repeat incident reuses its branch name; that is not an error."""
    def fake_request(method, url, headers=None, json=None, timeout=None):
        if method == "GET" and "/git/ref/heads/main" in url:
            return _FakeResponse(200, {"object": {"sha": "sha"}})
        if method == "POST" and url.endswith("/git/refs"):
            return _FakeResponse(422, None, text='{"message":"Reference already exists"}')
        if method == "GET" and "/contents/" in url:
            return _FakeResponse(404, None, text="Not Found")
        if method == "PUT":
            return _FakeResponse(200, {"commit": {}})
        if method == "POST" and url.endswith("/pulls"):
            return _FakeResponse(201, {"number": 7, "html_url": "u"})
        raise AssertionError(f"unexpected: {method} {url}")

    import httpx
    monkeypatch.setattr(httpx, "request", fake_request)

    ref = RestGitHubClient("t", "o/r").open_pull_request(
        branch="fix/repeat", title="t", body="b", commit_message="c",
        file_changes={"f.py": "x"},
    )
    assert ref.number == 7


def test_rest_client_surfaces_a_real_api_error(monkeypatch):
    def fake_request(method, url, headers=None, json=None, timeout=None):
        return _FakeResponse(403, None, text='{"message":"Resource not accessible by token"}')

    import httpx
    monkeypatch.setattr(httpx, "request", fake_request)

    with pytest.raises(GitHubError, match="403"):
        RestGitHubClient("t", "o/r").open_pull_request(
            branch="b", title="t", body="b", commit_message="c",
            file_changes={"f.py": "x"},
        )


def test_rest_client_refuses_an_empty_pull_request():
    with pytest.raises(GitHubError, match="no file changes"):
        RestGitHubClient("t", "o/r").open_pull_request(
            branch="b", title="t", body="b", commit_message="c", file_changes={},
        )


# --------------------------------------------------------------------------
# Agent behaviour against a failing code host
# --------------------------------------------------------------------------

def test_github_failure_preserves_the_investigation():
    """
    An unreachable code host must not discard completed work.

    The diagnosis, patch, and validation stay on the incident so an operator
    can apply the fix by hand.
    """
    from sentinel_core.agents.detection_agent import detection_agent
    from sentinel_core.agents.diagnosis_agent import diagnosis_agent
    from sentinel_core.agents.remediation_agent import remediation_agent
    from sentinel_core.agents.validation_agent import validation_agent
    from sentinel_core.agents.github_agent import GitHubAgent

    class BrokenClient:
        def open_pull_request(self, **kwargs):
            raise GitHubError("503 Service Unavailable")

    incident = detection_agent.run({
        "incident_id": "INC-TEST-1",
        "title": "test",
        "severity": "HIGH",
        "anomalies": [],
    })
    incident = diagnosis_agent.run(incident)
    incident = remediation_agent.run(incident)
    incident = validation_agent.run(incident)

    result = GitHubAgent(client=BrokenClient()).run(incident)

    assert result.pull_request is None
    assert result.diagnosis is not None, "RCA must survive a PR failure"
    assert result.remediation is not None, "the patch must survive a PR failure"
    assert result.validation is not None
    assert any(log["event"] == "PULL_REQUEST_FAILED" for log in result.agent_logs)


PRE_FIX_CONFIG = '''"""Config module."""
from pydantic import BaseModel, Field


class RAGConfig(BaseModel):
    top_k: int = Field(default=5, description="chunks retrieved", ge=1, le=50)
    reranker_enabled: bool = Field(default=False, description="reranking stage")
    reranker_top_n: int = Field(default=5, description="retained after rerank")


def reset_to_healthy_baseline() -> RAGConfig:
    return RAGConfig(
        top_k=5,
        reranker_enabled=False,
        reranker_top_n=5,
    )
'''


def test_remediation_emits_committable_file_content():
    """
    The PR needs real file content, not just a display diff.

    Driven from known input rather than the live file, so the assertion holds
    regardless of what the config currently says on disk.
    """
    from sentinel_core.agents.remediation_agent import remediation_agent

    changes = remediation_agent._build_file_changes(PRE_FIX_CONFIG)
    assert "rag_service/config.py" in changes

    content = changes["rag_service/config.py"]
    assert "top_k: int = Field(default=8," in content
    assert "reranker_enabled: bool = Field(default=True," in content
    # Must be the whole module, not a fragment.
    assert "class RAGConfig" in content
    assert "def reset_to_healthy_baseline" in content


def test_remediation_also_patches_the_reset_baseline():
    """
    Patching the field declarations alone is not a fix.

    `reset_to_healthy_baseline()` builds RAGConfig from its own literals and
    `clear_chaos()` calls it, so a patch that skips it would be silently
    reverted the next time anything reset the service.
    """
    from sentinel_core.agents.remediation_agent import remediation_agent

    content = remediation_agent._build_file_changes(PRE_FIX_CONFIG)["rag_service/config.py"]
    reset_body = content.split("def reset_to_healthy_baseline")[1]

    assert "top_k=8," in reset_body, "reset baseline still returns the pre-fix top_k"
    assert "reranker_enabled=True," in reset_body, "reset baseline still disables the reranker"


def test_remediation_is_idempotent_on_already_fixed_content():
    """
    Re-running against already-patched content must produce no change set.

    An empty set makes the GitHub client refuse the PR, which is correct:
    opening one that changes nothing while claiming to fix an incident is
    worse than opening none.
    """
    from sentinel_core.agents.remediation_agent import remediation_agent

    once = remediation_agent._build_file_changes(PRE_FIX_CONFIG)["rag_service/config.py"]
    assert remediation_agent._build_file_changes(once) == {}


def test_remediation_refuses_unrecognized_config_shape():
    """An unexpected file must yield no patch rather than a partial one."""
    from sentinel_core.agents.remediation_agent import remediation_agent

    assert remediation_agent._build_file_changes("totally unrelated content") == {}


# --------------------------------------------------------------------------
# API surface
# --------------------------------------------------------------------------

def test_health_endpoint_reports_deployment_posture():
    from api.server import app

    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "deployment_mode" in body
        assert body["github_integration"] in {"live", "simulated"}
        assert "config_warnings" in body
