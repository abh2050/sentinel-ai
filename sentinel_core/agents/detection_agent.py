"""
Detection & Triage Agent
Classifies incident severity, correlates metric anomalies, and initializes investigation state.
"""
import time
from typing import Dict, Any, List
from sentinel_core.models import IncidentRecord, IncidentSeverity, IncidentStatus, AnomalyItem
from sentinel_core.safety_policy import safety_enforcer

class DetectionAgent:
    def __init__(self):
        self.agent_name = "Sentinel Detection Agent"

    def run(self, incident_data: Dict[str, Any]) -> IncidentRecord:
        safety_enforcer.check_permission("DETECT_INCIDENT", self.agent_name)
        
        inc_id = incident_data.get("incident_id", f"INC-2026-{int(time.time())%10000:04d}")
        raw_severity = incident_data.get("severity", "HIGH")
        
        severity_map = {
            "CRITICAL": IncidentSeverity.P1_CRITICAL,
            "HIGH": IncidentSeverity.P2_HIGH,
            "MEDIUM": IncidentSeverity.P3_MEDIUM,
            "LOW": IncidentSeverity.P4_LOW
        }
        severity = severity_map.get(raw_severity, IncidentSeverity.P2_HIGH)
        
        anomalies = [
            AnomalyItem(**a) for a in incident_data.get("anomalies", [])
        ]
        
        title = incident_data.get("title", f"Production Incident {inc_id}")
        
        incident = IncidentRecord(
            incident_id=inc_id,
            title=title,
            severity=severity,
            status=IncidentStatus.INVESTIGATING,
            detected_at=time.time(),
            anomalies=anomalies,
            agent_logs=[{
                "timestamp": time.time(),
                "agent": self.agent_name,
                "event": "INCIDENT_TRIAGED",
                "details": f"Triaged incident {inc_id} with severity {severity.value}. Detected {len(anomalies)} metric anomalies. Initiating deep root-cause diagnosis."
            }]
        )
        return incident

detection_agent = DetectionAgent()
