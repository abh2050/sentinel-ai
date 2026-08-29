"""
Diagnosis & Root Cause Analysis (RCA) Agent

The one stage of the pipeline where a language model does the work. Root-cause
analysis is open-ended: the evidence is heterogeneous, the space of causes is
not enumerable in advance, and the useful output is an explanation of a
mechanism rather than a classification.

The agent is given read-only investigation tools and decides for itself what to
look at -- metrics against baseline, the live retrieval config, the change
history, the operational runbooks -- then submits a structured verdict.

When no model is configured, it falls back to a deterministic rule set so the
incident pipeline never stalls on a missing API key.
"""
import logging
import time
from typing import Dict, Any, Optional

from sentinel_core.models import IncidentRecord, DiagnosisReport, IncidentStatus
from sentinel_core.safety_policy import safety_enforcer
from sentinel_core.integrations.llm_client import (
    DeterministicDiagnosisClient,
    DiagnosisClient,
    DiagnosisContext,
    LLMError,
)
from rag_service.config import get_config

logger = logging.getLogger("sentinel.agents.diagnosis")


class DiagnosisAgent:
    def __init__(self, client: Optional[DiagnosisClient] = None):
        self.agent_name = "Sentinel Diagnosis Agent"
        # Injected for tests; otherwise resolved from settings on first use so
        # importing this module never requires an API key.
        self._client = client

    @property
    def client(self) -> DiagnosisClient:
        if self._client is None:
            from sentinel_core.integrations.llm_client import build_diagnosis_client
            self._client = build_diagnosis_client()
        return self._client

    def run(self, incident: IncidentRecord) -> IncidentRecord:
        safety_enforcer.check_permission("RUN_DIAGNOSIS", self.agent_name)

        context = self._build_context(incident)

        try:
            result = self.client.diagnose(context)
        except LLMError as exc:
            # A model outage must not cost us the incident. Fall back, and say
            # so in the log rather than presenting rule-based output as though
            # the model produced it.
            logger.warning("LLM diagnosis failed (%s); falling back to rule set", exc)
            incident.agent_logs.append({
                "timestamp": time.time(),
                "agent": self.agent_name,
                "event": "RCA_LLM_FALLBACK",
                "details": f"Model-backed diagnosis unavailable ({exc}). Used deterministic analysis.",
            })
            result = DeterministicDiagnosisClient().diagnose(context)

        diagnosis_report = DiagnosisReport(
            incident_id=incident.incident_id,
            confidence=result.confidence,
            root_cause_title=result.root_cause_title,
            root_cause_summary=result.root_cause_summary,
            evidence_items=result.evidence_items,
            suspect_file=result.suspect_file,
            suspect_changes=result.suspect_changes,
            analysis_source=result.model,
            llm_backed=result.llm_backed,
            investigation_log=result.investigation_log,
            created_at=time.time(),
        )

        incident.diagnosis = diagnosis_report
        incident.status = IncidentStatus.DIAGNOSED

        source = f"{result.model} ({len(result.investigation_log)} tool calls)" if result.llm_backed else "deterministic rule set"
        incident.agent_logs.append({
            "timestamp": time.time(),
            "agent": self.agent_name,
            "event": "RCA_COMPLETE",
            "details": (
                f"Root cause analysis complete via {source} with "
                f"{diagnosis_report.confidence * 100:.0f}% confidence: "
                f"{result.root_cause_title}"
            ),
        })
        return incident

    def _build_context(self, incident: IncidentRecord) -> DiagnosisContext:
        """Assemble everything the diagnosing agent is permitted to read."""
        from observability.metrics_collector import metrics_collector
        from observability.anomaly_detector import anomaly_detector

        cfg = get_config()
        snapshot = metrics_collector.get_current_metrics()
        # The rolling timeseries is large and adds nothing to causal reasoning;
        # the aggregates carry the signal.
        snapshot = {k: v for k, v in snapshot.items() if k != "timeseries"}

        return DiagnosisContext(
            incident_id=incident.incident_id,
            title=incident.title,
            severity=incident.severity.value if hasattr(incident.severity, "value") else str(incident.severity),
            anomalies=[a.model_dump() for a in incident.anomalies],
            metrics_snapshot=snapshot,
            baseline=dict(anomaly_detector.baseline),
            active_config=cfg.model_dump(),
            config_history=self._config_history(cfg),
        )

    @staticmethod
    def _config_history(cfg) -> list:
        """
        Recent configuration changes.

        The demo derives this by diffing the active config against the known
        healthy baseline. A production deployment would source it from the
        config-management audit log or deployment events instead -- the shape
        the agent consumes stays the same.
        """
        healthy = {"top_k": 5, "reranker_enabled": False, "similarity_threshold": 0.68}
        changes = []
        for key, baseline_value in healthy.items():
            current = getattr(cfg, key, None)
            if current != baseline_value:
                changes.append({
                    "parameter": key,
                    "previous_value": baseline_value,
                    "current_value": current,
                    "source": "runtime configuration diff vs healthy baseline",
                })
        return changes


diagnosis_agent = DiagnosisAgent()
