"""
AI Safety Covenant & Governance Enforcer
Strictly enforces human-in-the-loop policies for autonomous AI reliability engineering.
"""
from typing import Dict, Any, List
import time

class SafetyPolicyViolation(Exception):
    pass

class SafetyPolicyEnforcer:
    """
    Guarantees that AI may propose, branch, validate, and open PRs,
    but NEVER merge to production or override safety rules without human authorization.
    """
    PERMITTED_AI_ACTIONS = {
        "DETECT_INCIDENT",
        "INVESTIGATE_METRICS",
        "RUN_DIAGNOSIS",
        "SYNTHESIZE_CODE_FIX",
        "EXECUTE_SANDBOX_TESTS",
        "RUN_RAG_EVALUATIONS",
        "CREATE_GIT_BRANCH",
        "OPEN_PULL_REQUEST",
        "ADD_PR_COMMENT",
        "REQUEST_HUMAN_REVIEW"
    }

    FORBIDDEN_AI_ACTIONS = {
        "AUTO_MERGE_PULL_REQUEST",
        "DIRECT_PUSH_TO_MAIN",
        "DEPLOY_TO_PRODUCTION",
        "OVERRIDE_FAILED_TESTS",
        "DISABLE_MONITORING_RULES",
        "BYPASS_SANDBOX"
    }

    def __init__(self):
        self.audit_log: List[Dict[str, Any]] = []

    def check_permission(self, action: str, actor: str = "AI_AGENT") -> bool:
        """
        Validates if an action is permitted by the Safety Covenant.
        """
        if actor == "HUMAN_OPERATOR":
            self.log_action(action, actor, True, "Authorized by Human Engineer")
            return True

        if action in self.FORBIDDEN_AI_ACTIONS:
            self.log_action(action, actor, False, f"BLOCKED: Action '{action}' is strictly forbidden for AI agents without human authorization.")
            raise SafetyPolicyViolation(f"Safety Violation: Autonomous agents are prohibited from executing '{action}'. Mandatory human review required.")

        if action in self.PERMITTED_AI_ACTIONS:
            self.log_action(action, actor, True, f"Permitted under autonomous reliability policy.")
            return True

        # Default deny unknown actions
        self.log_action(action, actor, False, f"BLOCKED: Unknown action '{action}'")
        raise SafetyPolicyViolation(f"Safety Violation: Action '{action}' is not on the permitted whitelist.")

    def log_action(self, action: str, actor: str, permitted: bool, details: str):
        now = time.time()
        self.audit_log.append({
            "timestamp": now,
            "time_str": time.strftime("%H:%M:%S", time.localtime(now)),
            "agent_name": actor,
            "action": action,
            "is_permitted_by_safety": permitted,
            "status": "APPROVED" if permitted else "BLOCKED_BY_SAFETY_COVENANT",
            "details": details
        })

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        return list(reversed(self.audit_log))

safety_enforcer = SafetyPolicyEnforcer()
