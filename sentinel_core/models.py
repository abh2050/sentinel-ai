"""
Sentinel Core Domain Models
Pydantic schemas for incidents, agents, diagnostic reports, remediation proposals, and pull requests.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum
import time

class IncidentSeverity(str, Enum):
    P1_CRITICAL = "CRITICAL"
    P2_HIGH = "HIGH"
    P3_MEDIUM = "MEDIUM"
    P4_LOW = "LOW"

class IncidentStatus(str, Enum):
    DETECTED = "DETECTED"
    INVESTIGATING = "INVESTIGATING"
    DIAGNOSED = "DIAGNOSED"
    REMEDIATING = "REMEDIATING"
    VALIDATING = "VALIDATING"
    PR_CREATED = "PR_CREATED"
    AWAITING_HUMAN_REVIEW = "AWAITING_HUMAN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DEPLOYED = "DEPLOYED"

class AnomalyItem(BaseModel):
    metric: str
    title: str
    baseline: str
    current: str
    change_pct: str
    severity: str

class DiagnosisReport(BaseModel):
    incident_id: str
    confidence: float = Field(default=0.91, ge=0.0, le=1.0)
    root_cause_title: str
    root_cause_summary: str
    evidence_items: List[str]
    suspect_file: str = "rag_service/config.py"
    suspect_changes: Dict[str, Any] = {}
    created_at: float = Field(default_factory=time.time)

class RemediationProposal(BaseModel):
    incident_id: str
    summary: str
    branch_name: str
    commit_message: str
    file_path: str
    diff: str
    remediation_strategy: str
    created_at: float = Field(default_factory=time.time)

class ValidationMetricComparison(BaseModel):
    metric_name: str
    before_value: str
    after_value: str
    improvement: str
    status: str = "PASS"

class ValidationResult(BaseModel):
    incident_id: str
    passed: bool
    unit_tests_passed: bool
    integration_tests_passed: bool
    rag_eval_passed: bool
    regression_detected: bool = False
    metric_comparisons: List[ValidationMetricComparison]
    execution_logs: str
    validation_duration_seconds: float = 2.4
    created_at: float = Field(default_factory=time.time)

class PullRequestStatus(str, Enum):
    OPEN = "OPEN"
    APPROVED = "APPROVED"
    MERGED = "MERGED"
    REJECTED = "REJECTED"

class PullRequestPayload(BaseModel):
    incident_id: str
    pr_number: int
    pr_url: str
    branch_name: str
    title: str
    body_markdown: str
    diff: str
    status: PullRequestStatus = PullRequestStatus.OPEN
    author: str = "SentinelAI Autonomous Reliability Agent <sentinel-agent@sentinelai.internal>"
    human_review_required: bool = True
    merged_by: Optional[str] = None
    merged_at: Optional[float] = None
    created_at: float = Field(default_factory=time.time)

class IncidentRecord(BaseModel):
    incident_id: str
    title: str
    severity: IncidentSeverity
    status: IncidentStatus
    detected_at: float = Field(default_factory=time.time)
    anomalies: List[AnomalyItem]
    diagnosis: Optional[DiagnosisReport] = None
    remediation: Optional[RemediationProposal] = None
    validation: Optional[ValidationResult] = None
    pull_request: Optional[PullRequestPayload] = None
    agent_logs: List[Dict[str, Any]] = []

class AuditLogEntry(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    time_str: str = ""
    agent_name: str
    action: str
    is_permitted_by_safety: bool
    status: str
    details: str
