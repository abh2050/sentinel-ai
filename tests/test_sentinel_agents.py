"""
Unit tests for Sentinel Multi-Agent Pipeline & Safety Governance.
"""
import pytest
from sentinel_core.agents.detection_agent import detection_agent
from sentinel_core.agents.diagnosis_agent import diagnosis_agent
from sentinel_core.agents.remediation_agent import remediation_agent
from sentinel_core.agents.validation_agent import validation_agent
from sentinel_core.agents.github_agent import github_agent
from sentinel_core.safety_policy import safety_enforcer, SafetyPolicyViolation

def test_safety_policy_enforcement():
    # AI should be allowed to run diagnosis and open PR
    assert safety_enforcer.check_permission("RUN_DIAGNOSIS", "AI_AGENT") is True
    assert safety_enforcer.check_permission("OPEN_PULL_REQUEST", "AI_AGENT") is True
    
    # AI MUST NOT be allowed to auto-merge or push to main
    with pytest.raises(SafetyPolicyViolation):
        safety_enforcer.check_permission("AUTO_MERGE_PULL_REQUEST", "AI_AGENT")
        
    with pytest.raises(SafetyPolicyViolation):
        safety_enforcer.check_permission("DIRECT_PUSH_TO_MAIN", "AI_AGENT")

def test_full_agent_cycle():
    # Inject the fault first. Validation measures the patch against the live
    # configuration, so running this against an already-healthy service would
    # correctly report no improvement -- the agents would be validating a fix
    # for a problem that isn't there.
    from rag_service.chaos_injector import inject_scenario, clear_chaos
    clear_chaos()
    inject_scenario("retriever_latency_spike")

    payload = {
        "incident_id": "INC-2026-0042",
        "severity": "HIGH",
        "title": "p95 Latency & Cost Surge",
        "anomalies": [{
            "metric": "p95_latency",
            "title": "p95 Latency Spike",
            "baseline": "2.1s",
            "current": "11.8s",
            "change_pct": "+462%",
            "severity": "HIGH"
        }]
    }
    
    # 1. Detect
    incident = detection_agent.run(payload)
    assert incident.incident_id == "INC-2026-0042"
    
    # 2. Diagnose
    incident = diagnosis_agent.run(incident)
    assert incident.diagnosis is not None
    assert incident.diagnosis.confidence >= 0.90
    
    # 3. Remediate
    incident = remediation_agent.run(incident)
    assert incident.remediation is not None
    assert "top_k" in incident.remediation.diff
    
    # 4. Validate
    incident = validation_agent.run(incident)
    assert incident.validation is not None
    assert incident.validation.passed is True
    
    # 5. Open PR
    incident = github_agent.run(incident)
    assert incident.pull_request is not None
    assert incident.pull_request.human_review_required is True

    clear_chaos()
