"""
SentinelAI Fast API Mission Control Backend
Exposes endpoints for telemetry, incidents, chaos simulation, PR diff reviews, and human approvals.
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import asyncio
import time

from rag_service.config import get_config, reset_to_healthy_baseline
from rag_service.rag_engine import rag_engine
from rag_service.chaos_injector import inject_scenario, clear_chaos, get_active_chaos, SCENARIOS
from observability.metrics_collector import metrics_collector
from observability.anomaly_detector import anomaly_detector
from sentinel_core.orchestrator import orchestrator
from sentinel_core.safety_policy import safety_enforcer
from api.traffic_generator import traffic_generator
from api.ingestion_service import ingestion_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await traffic_generator.start()
    yield
    # Shutdown
    await traffic_generator.stop()

app = FastAPI(
    title="SentinelAI Reliability Mission Control",
    description="Autonomous AI Reliability & Incident Response Platform with Automated PR Remediation",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- TELEMETRY & SYSTEM HEALTH -----------------

@app.get("/api/status")
async def get_system_status():
    current_metrics = metrics_collector.get_current_metrics()
    active_chaos = get_active_chaos()
    return {
        "status": "HEALTHY" if not active_chaos else "INCIDENT_ACTIVE",
        "active_chaos_scenario": active_chaos,
        "config": get_config().model_dump(),
        "metrics_summary": {
            "p95_latency": current_metrics.get("p95_latency", 2.1),
            "avg_cost_usd": current_metrics.get("avg_cost_usd", 0.03),
            "avg_groundedness": current_metrics.get("avg_groundedness", 94.0),
            "avg_chunks": current_metrics.get("avg_chunks", 5.0)
        }
    }

@app.get("/api/metrics/live")
async def get_live_metrics():
    return metrics_collector.get_current_metrics()

# ----------------- TELEMETRY INGESTION PIPELINE -----------------

@app.get("/api/ingestion/sources")
async def list_ingestion_sources():
    """Connector inventory: which telemetry backends are wired up."""
    return ingestion_service.describe_sources()


@app.post("/api/ingestion/run")
async def run_ingestion_cycle():
    """
    Execute one extract -> normalize -> validate -> load cycle.

    Runs off the event loop: connectors perform blocking file and HTTP reads,
    which would otherwise stall every other request for the duration.
    """
    try:
        report = await asyncio.to_thread(ingestion_service.run_once)
        return {"success": True, "report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ingestion/report")
async def get_last_ingestion_report():
    """Most recent run report, or nulls before the first run."""
    report = ingestion_service.last_report()
    return {"has_run": report is not None, "report": report}


@app.post("/api/ingestion/reset")
async def reset_ingestion_watermarks():
    """Rewind all source watermarks so the next run replays from the start."""
    return ingestion_service.reset()


# ----------------- CHAOS & INCIDENT INJECTION -----------------

class ChaosTriggerRequest(BaseModel):
    scenario_id: str

@app.get("/api/chaos/scenarios")
async def list_chaos_scenarios():
    return SCENARIOS

@app.post("/api/chaos/trigger")
async def trigger_chaos_incident(req: ChaosTriggerRequest):
    try:
        inject_res = inject_scenario(req.scenario_id)
        for _ in range(5):
            res = rag_engine.query("How does Raft handle leader partition?")
            metrics_collector.record_query_event(res)
            
        detected = anomaly_detector.check_for_anomalies()
        incident_id = None
        if detected:
            incident = await orchestrator.handle_detected_incident(detected)
            incident_id = incident.incident_id
            
        return {
            "success": True,
            "chaos_result": inject_res,
            "incident_triggered": incident_id,
            "message": f"Injected '{req.scenario_id}'. Sentinel agents activated."
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/chaos/reset")
async def reset_system():
    res = clear_chaos()
    return {"success": True, "details": res}

# ----------------- INCIDENTS & AGENT PIPELINE -----------------

@app.get("/api/incidents")
async def list_incidents():
    incidents = orchestrator.get_all_incidents()
    return [inc.model_dump() for inc in incidents]

@app.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: str):
    inc = orchestrator.get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return inc.model_dump()

@app.post("/api/incidents/{incident_id}/run-agents")
async def trigger_agent_pipeline_manual(incident_id: str):
    inc = orchestrator.get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    payload = {
        "incident_id": inc.incident_id,
        "title": inc.title,
        "severity": inc.severity.value,
        "anomalies": [a.model_dump() for a in inc.anomalies]
    }
    updated = await orchestrator.handle_detected_incident(payload)
    return updated.model_dump()

# ----------------- HUMAN REVIEW & PR MANAGEMENT -----------------

class HumanDecisionRequest(BaseModel):
    reviewer_name: str = "Lead SRE Engineer"
    reason: Optional[str] = "Approved after code review and validation verification."

@app.post("/api/incidents/{incident_id}/pr/approve")
async def approve_and_merge_pr(incident_id: str, req: HumanDecisionRequest):
    try:
        updated = orchestrator.approve_and_merge_pr(incident_id, reviewer_name=req.reviewer_name)
        for _ in range(10):
            res = rag_engine.query("What are vector database indexing best practices?")
            metrics_collector.record_query_event(res)
        return {"success": True, "incident": updated.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/incidents/{incident_id}/pr/reject")
async def reject_pr(incident_id: str, req: HumanDecisionRequest):
    try:
        updated = orchestrator.reject_pr(incident_id, reviewer_name=req.reviewer_name, reason=req.reason or "")
        return {"success": True, "incident": updated.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ----------------- AUDIT TRAIL -----------------

@app.get("/api/audit-trail")
async def get_audit_trail():
    return safety_enforcer.get_audit_trail()
