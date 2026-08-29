"""
Sentinel Multi-Agent Orchestrator
Coordinates the full lifecycle: Detection -> Diagnosis -> Remediation -> Sandbox Validation -> GitHub PR -> Human Review.
"""
import time
import asyncio
from typing import Dict, Any, List, Optional
from sentinel_core.models import IncidentRecord, IncidentStatus, PullRequestStatus
from sentinel_core.agents.detection_agent import detection_agent
from sentinel_core.agents.diagnosis_agent import diagnosis_agent
from sentinel_core.agents.remediation_agent import remediation_agent
from sentinel_core.agents.validation_agent import validation_agent
from sentinel_core.agents.github_agent import github_agent
from sentinel_core.safety_policy import safety_enforcer
from rag_service.config import update_config_fields, reset_to_healthy_baseline
from rag_service.chaos_injector import clear_chaos

class SentinelOrchestrator:
    def __init__(self):
        self.active_incidents: Dict[str, IncidentRecord] = {}

    def get_all_incidents(self) -> List[IncidentRecord]:
        return list(self.active_incidents.values())

    def get_incident(self, incident_id: str) -> Optional[IncidentRecord]:
        return self.active_incidents.get(incident_id)

    async def handle_detected_incident(self, incident_payload: Dict[str, Any]) -> IncidentRecord:
        """
        Executes the autonomous multi-agent pipeline from detection to PR opening.
        """
        # 1. Detection Agent
        incident = detection_agent.run(incident_payload)
        self.active_incidents[incident.incident_id] = incident
        await asyncio.sleep(0.1)

        # 2. Diagnosis Agent
        incident = diagnosis_agent.run(incident)
        await asyncio.sleep(0.1)

        # 3. Remediation Agent
        incident = remediation_agent.run(incident)
        await asyncio.sleep(0.1)

        # 4. Validation Sandbox Agent
        incident = validation_agent.run(incident)
        await asyncio.sleep(0.1)

        # 5. GitHub Integration Agent
        incident = github_agent.run(incident)
        
        return incident

    def approve_and_merge_pr(self, incident_id: str, reviewer_name: str = "Human Lead SRE") -> IncidentRecord:
        """
        Human engineer authorizes and merges the PR. Applies the fix to production.
        """
        incident = self.active_incidents.get(incident_id)
        if not incident:
            raise ValueError(f"Incident {incident_id} not found.")

        # Safety permission check for human authorization
        safety_enforcer.check_permission("APPROVE_AND_MERGE_PR", "HUMAN_OPERATOR")

        # Clear chaos state and apply the validated fix to active production configuration
        clear_chaos()
        update_config_fields(top_k=8, reranker_enabled=True, reranker_top_n=5)

        now = time.time()
        if incident.pull_request:
            incident.pull_request.status = PullRequestStatus.MERGED
            incident.pull_request.merged_by = reviewer_name
            incident.pull_request.merged_at = now

        incident.status = IncidentStatus.DEPLOYED
        incident.agent_logs.append({
            "timestamp": now,
            "agent": "HUMAN_OPERATOR",
            "event": "PR_APPROVED_AND_MERGED",
            "details": f"PR approved and merged by {reviewer_name}. Fix deployed to production. Latency and cost restored to healthy baseline."
        })
        return incident

    def reject_pr(self, incident_id: str, reviewer_name: str = "Human Lead SRE", reason: str = "Rejected by reviewer.") -> IncidentRecord:
        """
        Human engineer rejects the proposed fix.
        """
        incident = self.active_incidents.get(incident_id)
        if not incident:
            raise ValueError(f"Incident {incident_id} not found.")

        safety_enforcer.check_permission("REJECT_PULL_REQUEST", "HUMAN_OPERATOR")

        now = time.time()
        if incident.pull_request:
            incident.pull_request.status = PullRequestStatus.REJECTED

        incident.status = IncidentStatus.REJECTED
        incident.agent_logs.append({
            "timestamp": now,
            "agent": "HUMAN_OPERATOR",
            "event": "PR_REJECTED",
            "details": f"PR rejected by {reviewer_name}. Reason: {reason}"
        })
        return incident

orchestrator = SentinelOrchestrator()
