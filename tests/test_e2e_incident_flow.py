"""
End-to-End Test: Chaos Injection -> Detection -> Multi-Agent Pipeline -> Human PR Approval -> Recovery.
"""
import pytest
import asyncio
from rag_service.chaos_injector import inject_scenario, clear_chaos
from rag_service.config import get_config
from rag_service.rag_engine import rag_engine
from observability.metrics_collector import metrics_collector
from observability.anomaly_detector import anomaly_detector
from sentinel_core.orchestrator import orchestrator
from sentinel_core.models import PullRequestStatus, IncidentStatus

def test_e2e_incident_and_human_approval_flow():
    async def run_flow():
        # 1. Clear state
        clear_chaos()
        
        # 2. Inject INC-2026-0042
        inject_res = inject_scenario("retriever_latency_spike")
        assert inject_res["status"] == "injected"
        assert get_config().top_k == 30
        
        # Generate anomalous telemetry events
        for _ in range(8):
            res = rag_engine.query("What causes latency spike in RAG?")
            metrics_collector.record_query_event(res)
        
        # 3. Detect anomaly
        detected = anomaly_detector.check_for_anomalies()
        assert detected is not None
        assert detected["severity"] == "HIGH"
        
        # 4. Orchestrate agents
        incident = await orchestrator.handle_detected_incident(detected)
        assert incident.status == IncidentStatus.AWAITING_HUMAN_REVIEW
        assert incident.pull_request is not None
        assert incident.pull_request.status == PullRequestStatus.OPEN
        
        # 5. Human reviews and approves PR
        resolved_incident = orchestrator.approve_and_merge_pr(incident.incident_id, reviewer_name="Sarah Chen (Staff SRE)")
        assert resolved_incident.status == IncidentStatus.DEPLOYED
        assert resolved_incident.pull_request.status == PullRequestStatus.MERGED
        assert resolved_incident.pull_request.merged_by == "Sarah Chen (Staff SRE)"
        
        # 6. Verify config restored and optimized
        assert get_config().top_k == 8
        assert get_config().reranker_enabled is True
        
    asyncio.run(run_flow())
