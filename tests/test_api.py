"""
API Integration Tests for SentinelAI Fast API server.
"""
import pytest
from starlette.testclient import TestClient
from api.server import app
from rag_service.chaos_injector import clear_chaos

client = TestClient(app)

def test_api_status_endpoint():
    clear_chaos()
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ["HEALTHY", "INCIDENT_ACTIVE"]
    assert "metrics_summary" in data

def test_api_metrics_live():
    resp = client.get("/api/metrics/live")
    assert resp.status_code == 200
    data = resp.json()
    assert "p95_latency" in data
    assert "avg_cost_usd" in data
    assert "timeseries" in data

def test_api_chaos_and_pr_approval_workflow():
    clear_chaos()
    
    # 1. Trigger chaos incident
    chaos_resp = client.post("/api/chaos/trigger", json={"scenario_id": "retriever_latency_spike"})
    assert chaos_resp.status_code == 200
    chaos_data = chaos_resp.json()
    assert chaos_data["success"] is True
    incident_id = chaos_data["incident_triggered"]
    assert incident_id is not None
    
    # 2. Get incident details
    inc_resp = client.get(f"/api/incidents/{incident_id}")
    assert inc_resp.status_code == 200
    inc_data = inc_resp.json()
    assert inc_data["status"] == "AWAITING_HUMAN_REVIEW"
    assert inc_data["pull_request"] is not None
    assert inc_data["pull_request"]["status"] == "OPEN"
    assert inc_data["pull_request"]["human_review_required"] is True
    
    # 3. Approve PR as human reviewer
    approve_resp = client.post(
        f"/api/incidents/{incident_id}/pr/approve",
        json={"reviewer_name": "Devin Torres (Staff SRE)", "reason": "Verified fix reduces p95 latency by 79%."}
    )
    assert approve_resp.status_code == 200
    approve_data = approve_resp.json()
    assert approve_data["success"] is True
    assert approve_data["incident"]["status"] == "DEPLOYED"
    assert approve_data["incident"]["pull_request"]["status"] == "MERGED"
    assert approve_data["incident"]["pull_request"]["merged_by"] == "Devin Torres (Staff SRE)"
    
    # 4. Check audit trail
    audit_resp = client.get("/api/audit-trail")
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert len(audit_data) > 0
    assert any(a["action"] == "APPROVE_AND_MERGE_PR" for a in audit_data)
