"""
Remediation Agent
Synthesizes surgical code and configuration patches, git branch names, commit messages, and PR descriptions.
"""
import time
from typing import Dict, Any
from sentinel_core.models import IncidentRecord, RemediationProposal, IncidentStatus
from sentinel_core.safety_policy import safety_enforcer

class RemediationAgent:
    def __init__(self):
        self.agent_name = "Sentinel Remediation Agent"

    def run(self, incident: IncidentRecord) -> IncidentRecord:
        safety_enforcer.check_permission("SYNTHESIZE_CODE_FIX", self.agent_name)
        
        inc_id = incident.incident_id
        branch_name = f"fix/{inc_id.lower()}-retriever-latency"
        commit_msg = f"fix(rag): optimize retrieval volume to top_k=8 and enable reranker after {inc_id}"
        
        # Proposed surgical diff
        proposed_diff = """--- a/rag_service/config.py
+++ b/rag_service/config.py
@@ -10,7 +10,7 @@ class RAGConfig(BaseModel):
     # Retrieval Configuration
-    top_k: int = Field(default=30, description="Number of chunks retrieved from vector store", ge=1, le=50)
+    top_k: int = Field(default=8, description="Number of chunks retrieved from vector store", ge=1, le=50)
     similarity_threshold: float = Field(default=0.68, description="Minimum cosine similarity score", ge=0.0, le=1.0)
     
     # Reranker Configuration
-    reranker_enabled: bool = Field(default=False, description="Enable cross-encoder reranking stage")
+    reranker_enabled: bool = Field(default=True, description="Enable cross-encoder reranking stage")
-    reranker_top_n: int = Field(default=5, description="Number of chunks retained after reranking", ge=1, le=20)
+    reranker_top_n: int = Field(default=5, description="Number of chunks retained after reranking", ge=1, le=20)
"""
        
        proposal = RemediationProposal(
            incident_id=inc_id,
            summary="Reduce retrieval top_k from 30 to 8, enable cross-encoder reranking (top_n=5), and bound max context tokens.",
            branch_name=branch_name,
            commit_message=commit_msg,
            file_path="rag_service/config.py",
            diff=proposed_diff,
            remediation_strategy="Two-stage retrieval architecture: Candidate retrieval with top_k=8 + Flash-Reranker filtering to top_n=5 most relevant chunks.",
            created_at=time.time()
        )
        
        incident.remediation = proposal
        incident.status = IncidentStatus.REMEDIATING
        incident.agent_logs.append({
            "timestamp": time.time(),
            "agent": self.agent_name,
            "event": "REMEDIATION_SYNTHESIZED",
            "details": f"Generated surgical patch for 'rag_service/config.py'. Target branch: '{branch_name}'."
        })
        return incident

remediation_agent = RemediationAgent()
