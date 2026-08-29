"""
Remediation Agent
Synthesizes surgical code and configuration patches, git branch names, commit messages, and PR descriptions.
"""
import re
import time
from pathlib import Path
from typing import Dict, Any, Optional
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
            file_changes=self._build_file_changes(),
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

    # Every place the healthy retrieval defaults are expressed. Patching only
    # the Field declarations is not enough: `reset_to_healthy_baseline()`
    # constructs RAGConfig with its own literals, and `clear_chaos()` calls it.
    # A fix applied to the declarations alone would be silently reverted the
    # next time anything reset the service.
    CONFIG_SUBSTITUTIONS = [
        # Pydantic field declarations
        (r"(top_k:\s*int\s*=\s*Field\(default=)\d+", r"\g<1>8"),
        (r"(reranker_enabled:\s*bool\s*=\s*Field\(default=)(True|False)", r"\g<1>True"),
        # Literals inside reset_to_healthy_baseline()
        (r"(\n\s+top_k=)\d+(,)", r"\g<1>8\g<2>"),
        (r"(\n\s+reranker_enabled=)(True|False)(,)", r"\g<1>True\g<3>"),
    ]

    def _build_file_changes(self, source_content: Optional[str] = None) -> Dict[str, str]:
        """
        Produce the actual post-fix file content to commit.

        Reads the current file and applies the parameter changes to it, rather
        than shipping a hardcoded copy: a stored snapshot would silently revert
        every unrelated edit made to the config since this agent was written.

        Returns an empty change set when the file cannot be read, when it no
        longer matches what this remediation expects, or when the fix is
        already applied. Empty makes the GitHub client refuse to open the PR,
        which is the right outcome in all three cases -- better no pull request
        than one that changes nothing while claiming to fix an incident.

        `source_content` is for testing the transform against known input
        without depending on the state of the file on disk.
        """
        if source_content is None:
            source_path = Path(__file__).resolve().parents[2] / "rag_service" / "config.py"
            try:
                source_content = source_path.read_text(encoding="utf-8")
            except OSError:
                return {}

        # Match whatever value is currently declared rather than the incident's
        # runtime value. The injected fault (top_k=30) is an in-memory mutation
        # that never reaches the file, so matching on it would patch nothing.
        patched = source_content
        for pattern, replacement in self.CONFIG_SUBSTITUTIONS:
            patched, count = re.subn(pattern, replacement, patched, count=1)
            if count == 0:
                return {}

        if patched == source_content:
            return {}

        return {"rag_service/config.py": patched}


remediation_agent = RemediationAgent()
