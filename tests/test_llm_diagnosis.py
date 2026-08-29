"""
LLM-Backed Diagnosis Tests

Covers the model-backed diagnosis path without making a network call: the tool
closures, verdict capture, result mapping, provenance, and every degradation
path. A fake runner drives the same code the SDK would drive, so the agent's
own logic is exercised rather than mocked away.
"""
import json

import pytest

from sentinel_core.integrations.llm_client import (
    AnthropicDiagnosisAgent,
    DeterministicDiagnosisClient,
    DiagnosisContext,
    DiagnosisResult,
    LLMError,
    _clamp_confidence,
    _coerce_changes,
    build_diagnosis_client,
)
from sentinel_core.settings import Settings


def _context() -> DiagnosisContext:
    return DiagnosisContext(
        incident_id="INC-2026-0042",
        title="p95 Latency & Cost Surge",
        severity="HIGH",
        anomalies=[{"metric": "p95_latency", "current": "11.8s", "baseline": "2.1s"}],
        metrics_snapshot={"p95_latency": 11.8, "avg_cost_usd": 0.14, "avg_chunks": 30.0},
        baseline={"p95_latency": 2.1, "avg_cost_usd": 0.03, "avg_chunks": 5.0},
        active_config={"top_k": 30, "reranker_enabled": False, "chunk_size": 512},
        config_history=[{"parameter": "top_k", "previous_value": 5, "current_value": 30}],
    )


# --------------------------------------------------------------------------
# Deterministic fallback
# --------------------------------------------------------------------------

def test_deterministic_client_produces_a_usable_verdict():
    result = DeterministicDiagnosisClient().diagnose(_context())

    assert result.llm_backed is False
    assert result.model == "deterministic"
    assert 0.0 <= result.confidence <= 1.0
    assert result.evidence_items
    assert "top_k" in result.root_cause_summary or "30" in result.root_cause_summary


def test_deterministic_client_reflects_the_actual_config():
    """The fallback must read the live config, not quote fixed numbers."""
    context = _context()
    context.active_config = {"top_k": 12, "reranker_enabled": False, "chunk_size": 256}

    result = DeterministicDiagnosisClient().diagnose(context)
    assert "12" in " ".join(result.evidence_items)


# --------------------------------------------------------------------------
# Client selection
# --------------------------------------------------------------------------

def test_no_api_key_selects_the_deterministic_client(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SENTINEL_ANTHROPIC_API_KEY", raising=False)
    client = build_diagnosis_client(Settings.from_env())
    assert isinstance(client, DeterministicDiagnosisClient)


def test_api_key_selects_the_model_backed_agent(monkeypatch):
    # Set both inputs explicitly. The sandbox validation run exports
    # SENTINEL_LLM_ENABLED=false so nested tests never call the API, and a test
    # that reads it from the ambient environment would fail only in there.
    monkeypatch.setenv("SENTINEL_LLM_ENABLED", "true")
    monkeypatch.setenv("SENTINEL_ANTHROPIC_API_KEY", "sk-ant-test")
    client = build_diagnosis_client(Settings.from_env())
    assert isinstance(client, AnthropicDiagnosisAgent)
    assert client.model == "claude-opus-5"


def test_llm_can_be_disabled_even_with_a_key_present(monkeypatch):
    """CI and cost-controlled runs need a hard off switch."""
    monkeypatch.setenv("SENTINEL_ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("SENTINEL_LLM_ENABLED", "false")
    assert isinstance(build_diagnosis_client(Settings.from_env()), DeterministicDiagnosisClient)


def test_standard_anthropic_env_var_is_honored(monkeypatch):
    """An already-configured environment should work without a rename."""
    monkeypatch.setenv("SENTINEL_LLM_ENABLED", "true")
    monkeypatch.delenv("SENTINEL_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-standard")
    assert Settings.from_env().llm.api_key == "sk-ant-standard"


# --------------------------------------------------------------------------
# The agent loop, driven by a fake runner
# --------------------------------------------------------------------------

class _FakeRunner:
    """
    Stands in for the SDK tool runner.

    Calls each investigation tool once, then submits a verdict -- the same
    sequence a real model run produces, so the agent's closures, capture, and
    mapping are genuinely exercised.
    """

    def __init__(self, tools, verdict=None, call_submit=True):
        self.tools = {t.name: t for t in tools}
        self.verdict = verdict or {
            "root_cause_title": "Retrieval Top-K Misconfiguration",
            "root_cause_summary": "top_k=30 without reranking saturated the context window.",
            "confidence": 0.93,
            "evidence_items": ["Active top_k is 30 against a baseline of 5."],
            "suspect_file": "rag_service/config.py",
            "suspect_changes": '{"top_k": 30}',
        }
        self.call_submit = call_submit

    def __iter__(self):
        self.tools["get_metrics_snapshot"].call({})
        self.tools["get_retrieval_config"].call({})
        self.tools["get_recent_changes"].call({})
        self.tools["search_runbooks"].call({"query": "context window latency"})
        if self.call_submit:
            self.tools["submit_diagnosis"].call(self.verdict)
        return iter([])


def _agent_with_fake(verdict=None, call_submit=True, knowledge=None):
    agent = AnthropicDiagnosisAgent(
        api_key="sk-ant-test",
        knowledge_lookup=knowledge or (lambda q: [{"title": "Token Economics", "content": "..."}]),
    )

    class FakeMessages:
        def tool_runner(self, **kwargs):
            return _FakeRunner(kwargs["tools"], verdict=verdict, call_submit=call_submit)

    class FakeBeta:
        messages = FakeMessages()

    class FakeClient:
        beta = FakeBeta()

    agent._client = lambda: FakeClient()
    return agent


def test_agent_captures_the_submitted_verdict():
    result = _agent_with_fake().diagnose(_context())

    assert result.llm_backed is True
    assert result.model == "claude-opus-5"
    assert result.root_cause_title == "Retrieval Top-K Misconfiguration"
    assert result.confidence == pytest.approx(0.93)
    assert result.suspect_changes == {"top_k": 30}


def test_agent_records_its_investigation_trail():
    """
    The reasoning path is part of the output, not just the conclusion.

    A reviewer weighing an RCA needs to see what the agent actually looked at.
    """
    result = _agent_with_fake().diagnose(_context())

    assert len(result.investigation_log) == 4
    joined = " ".join(result.investigation_log)
    assert "metrics" in joined
    assert "configuration" in joined
    assert "runbooks" in joined


def test_tools_return_the_live_context():
    """Each tool must surface real incident data, not placeholders."""
    captured = {}

    class CapturingRunner(_FakeRunner):
        def __iter__(self):
            captured["metrics"] = self.tools["get_metrics_snapshot"].call({})
            captured["config"] = self.tools["get_retrieval_config"].call({})
            captured["changes"] = self.tools["get_recent_changes"].call({})
            self.tools["submit_diagnosis"].call(self.verdict)
            return iter([])

    agent = _agent_with_fake()

    class FakeMessages:
        def tool_runner(self, **kwargs):
            return CapturingRunner(kwargs["tools"])

    class FakeBeta:
        messages = FakeMessages()

    class FakeClient:
        beta = FakeBeta()

    agent._client = lambda: FakeClient()
    agent.diagnose(_context())

    assert json.loads(captured["metrics"])["current"]["p95_latency"] == 11.8
    assert json.loads(captured["config"])["top_k"] == 30
    assert json.loads(captured["changes"])[0]["parameter"] == "top_k"


def test_agent_errors_when_no_verdict_is_submitted():
    with pytest.raises(LLMError, match="without submitting a diagnosis"):
        _agent_with_fake(call_submit=False).diagnose(_context())


def test_knowledge_lookup_failure_is_data_not_a_crash():
    """A failing tool should return an error string the model can react to."""
    def exploding(query):
        raise RuntimeError("index unavailable")

    result = _agent_with_fake(knowledge=exploding).diagnose(_context())
    assert result.llm_backed is True  # investigation continued regardless


def test_confidence_is_clamped_into_range():
    """DiagnosisReport rejects out-of-range confidence; clamp before it gets there."""
    assert _clamp_confidence(1.7) == 1.0
    assert _clamp_confidence(-0.2) == 0.0
    assert _clamp_confidence("not a number") == 0.8
    assert _clamp_confidence(0.87) == pytest.approx(0.87)


def test_suspect_changes_accepts_object_or_json_string():
    """Reject a correct diagnosis over a formatting detail is the wrong trade."""
    assert _coerce_changes('{"top_k": 30}') == {"top_k": 30}
    assert _coerce_changes({"top_k": 30}) == {"top_k": 30}
    assert _coerce_changes("not json") == {"note": "not json"}
    assert _coerce_changes(None) == {}


def test_out_of_range_confidence_survives_the_full_agent():
    result = _agent_with_fake(verdict={
        "root_cause_title": "t", "root_cause_summary": "s",
        "confidence": 4.2, "evidence_items": ["e"],
        "suspect_file": "f.py", "suspect_changes": "{}",
    }).diagnose(_context())
    assert result.confidence == 1.0


# --------------------------------------------------------------------------
# Integration with the diagnosis agent
# --------------------------------------------------------------------------

def test_diagnosis_agent_records_provenance_on_the_report():
    """A reviewer must be able to tell a model verdict from a rule-based one."""
    from sentinel_core.agents.detection_agent import detection_agent
    from sentinel_core.agents.diagnosis_agent import DiagnosisAgent

    incident = detection_agent.run({
        "incident_id": "INC-PROV-1", "title": "t", "severity": "HIGH", "anomalies": [],
    })

    agent = DiagnosisAgent(client=_agent_with_fake())
    incident = agent.run(incident)

    assert incident.diagnosis.llm_backed is True
    assert incident.diagnosis.analysis_source == "claude-opus-5"
    assert incident.diagnosis.investigation_log


def test_model_failure_falls_back_without_losing_the_incident():
    """
    A model outage must not cost the investigation.

    The incident continues on the deterministic path, and the log says so
    rather than presenting rule output as though the model produced it.
    """
    from sentinel_core.agents.detection_agent import detection_agent
    from sentinel_core.agents.diagnosis_agent import DiagnosisAgent

    class BrokenClient:
        def diagnose(self, context):
            raise LLMError("529 overloaded")

    incident = detection_agent.run({
        "incident_id": "INC-FALL-1", "title": "t", "severity": "HIGH", "anomalies": [],
    })
    incident = DiagnosisAgent(client=BrokenClient()).run(incident)

    assert incident.diagnosis is not None
    assert incident.diagnosis.llm_backed is False
    assert any(log["event"] == "RCA_LLM_FALLBACK" for log in incident.agent_logs)


def test_deterministic_path_marks_itself_as_not_llm_backed():
    from sentinel_core.agents.detection_agent import detection_agent
    from sentinel_core.agents.diagnosis_agent import DiagnosisAgent

    incident = detection_agent.run({
        "incident_id": "INC-DET-1", "title": "t", "severity": "HIGH", "anomalies": [],
    })
    incident = DiagnosisAgent(client=DeterministicDiagnosisClient()).run(incident)

    assert incident.diagnosis.llm_backed is False
    assert incident.diagnosis.analysis_source == "deterministic"


def test_tool_schemas_are_well_formed():
    """
    The SDK generates tool schemas from signatures and docstrings.

    A malformed annotation or a missing Args entry produces a schema the API
    rejects at call time -- catch that here instead of mid-incident.
    """
    captured = {}

    agent = AnthropicDiagnosisAgent(api_key="sk-ant-test")

    class FakeMessages:
        def tool_runner(self, **kwargs):
            captured["tools"] = kwargs["tools"]
            captured["model"] = kwargs["model"]
            captured["thinking"] = kwargs.get("thinking")
            raise LLMError("stop here")

    class FakeBeta:
        messages = FakeMessages()

    class FakeClient:
        beta = FakeBeta()

    agent._client = lambda: FakeClient()
    with pytest.raises(LLMError):
        agent.diagnose(_context())

    tools = captured["tools"]
    assert len(tools) == 5
    assert captured["model"] == "claude-opus-5"
    assert captured["thinking"] == {"type": "adaptive"}

    for tool in tools:
        schema = tool.input_schema
        assert schema["type"] == "object"
        assert "properties" in schema

    submit = next(t for t in tools if t.name == "submit_diagnosis")
    props = submit.input_schema["properties"]
    assert props["confidence"]["type"] == "number"
    assert props["evidence_items"]["type"] == "array"
    assert props["evidence_items"]["items"]["type"] == "string"
