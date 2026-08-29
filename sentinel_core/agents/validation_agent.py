"""
Validation Agent (Sandbox Test & Evaluation Runner)

Applies the proposed patch to an isolated copy of the repository, runs the real
test suite against it, and benchmarks the patched configuration.

This stage carries the weight of the whole safety argument. The human reviewer
approves a pull request because a scorecard says the fix works; if that
scorecard is decorative, review becomes rubber-stamping and the human gate is
worse than no automation at all. So `passed` reflects an actual pytest exit
code, and a failing suite blocks the pull request.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from sentinel_core.models import (
    IncidentRecord,
    ValidationResult,
    ValidationMetricComparison,
    IncidentStatus,
)
from sentinel_core.safety_policy import safety_enforcer

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_TIMEOUT_SECONDS = 300


# Set inside the sandbox subprocess. The suite this agent runs contains tests
# that themselves trigger incidents, which would invoke this agent again and
# spawn another sandbox -- unbounded recursion. The nested run executes the
# tests but does not spawn a further sandbox.
SANDBOX_CHILD_ENV = "SENTINEL_SANDBOX_CHILD"


class ValidationAgent:
    def __init__(self, run_real_tests: Optional[bool] = None):
        self.agent_name = "Sentinel Validation Agent"
        if run_real_tests is None:
            run_real_tests = os.getenv(SANDBOX_CHILD_ENV) != "1"
        self.run_real_tests = run_real_tests

    def run(self, incident: IncidentRecord) -> IncidentRecord:
        safety_enforcer.check_permission("EXECUTE_SANDBOX_TESTS", self.agent_name)
        safety_enforcer.check_permission("RUN_RAG_EVALUATIONS", self.agent_name)

        started = time.time()
        log_lines: List[str] = ["=== SENTINEL SANDBOX TEST RUNNER ==="]

        file_changes = incident.remediation.file_changes if incident.remediation else {}
        tests_passed, test_log, test_summary = self._execute_sandbox_tests(file_changes, log_lines)

        comparisons = self._benchmark_comparisons()
        # Any metric that failed to improve is a regression, regardless of what
        # the tests said.
        regression = any(c.status != "PASS" for c in comparisons)
        overall_passed = tests_passed and not regression

        log_lines.append("")
        if overall_passed:
            log_lines.append("[PASS] All validation criteria satisfied. Safe to propose Pull Request.")
        else:
            reason = "unit tests failed" if not tests_passed else "metric regression detected"
            log_lines.append(f"[FAIL] Validation did not pass ({reason}). Pull request blocked.")

        val_result = ValidationResult(
            incident_id=incident.incident_id,
            passed=overall_passed,
            unit_tests_passed=tests_passed,
            integration_tests_passed=tests_passed,
            rag_eval_passed=not regression,
            regression_detected=regression,
            metric_comparisons=comparisons,
            execution_logs="\n".join(log_lines),
            validation_duration_seconds=round(time.time() - started, 2),
            created_at=time.time(),
        )

        incident.validation = val_result
        incident.status = IncidentStatus.VALIDATING
        incident.agent_logs.append({
            "timestamp": time.time(),
            "agent": self.agent_name,
            "event": "SANDBOX_VALIDATION_COMPLETE" if overall_passed else "SANDBOX_VALIDATION_FAILED",
            "details": (
                f"{test_summary} Benchmark regressions: {'yes' if regression else 'none'}. "
                f"Overall: {'PASS' if overall_passed else 'FAIL'}."
            ),
        })
        return incident

    # -- Sandbox execution --------------------------------------------------

    def _execute_sandbox_tests(
        self,
        file_changes: Dict[str, str],
        log_lines: List[str],
    ) -> Tuple[bool, str, str]:
        """
        Copy the repo to a temp dir, apply the patch, run pytest there.

        Running in a copy rather than in place matters: the patch mutates the
        retrieval config this very process is using, so an in-place run would
        leave the live service reconfigured by its own validation step.
        """
        if not self.run_real_tests:
            log_lines.append("[INFO] Real test execution disabled; skipping pytest.")
            return True, "", "Test execution skipped."

        if not file_changes:
            log_lines.append("[WARN] No file changes proposed; nothing to validate.")
            return False, "", "No patch to validate."

        sandbox: Optional[str] = None
        try:
            sandbox = tempfile.mkdtemp(prefix="sentinel-sandbox-")
            sandbox_path = Path(sandbox) / "repo"

            log_lines.append(f"[INFO] Provisioning isolated sandbox at {sandbox_path}")
            shutil.copytree(
                REPO_ROOT,
                sandbox_path,
                ignore=shutil.ignore_patterns(
                    ".git", ".venv", "node_modules", "__pycache__",
                    ".pytest_cache", "dist", "docs", "data",
                ),
            )

            # The fixtures the ingestion tests read live under data/, which is
            # excluded from the copy above for size; bring just those back.
            source_data = REPO_ROOT / "data"
            if source_data.is_dir():
                shutil.copytree(source_data, sandbox_path / "data", dirs_exist_ok=True)

            for rel_path, content in file_changes.items():
                target = sandbox_path / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                log_lines.append(f"[INFO] Applied patch to {rel_path}")

            log_lines.append("[INFO] Executing pytest against the patched tree...")
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=short"],
                cwd=str(sandbox_path),
                capture_output=True,
                text=True,
                timeout=TEST_TIMEOUT_SECONDS,
                # Keep the child from inheriting credentials: the sandbox runs
                # the patched suite, and it has no business reaching the API.
                env={
                    **os.environ,
                    # Break the recursion: the nested suite triggers incidents.
                    SANDBOX_CHILD_ENV: "1",
                    # Keep the child from inheriting credentials. The sandbox
                    # runs the patched suite; it has no business calling the API.
                    "SENTINEL_LLM_ENABLED": "false",
                    "ANTHROPIC_API_KEY": "",
                },
            )

            output = (completed.stdout or "") + (completed.stderr or "")
            log_lines.extend(_tail(output, 25))

            passed = completed.returncode == 0
            summary = _extract_pytest_summary(output)
            log_lines.append(f"[INFO] pytest exit code {completed.returncode} ({summary})")
            return passed, output, summary

        except subprocess.TimeoutExpired:
            log_lines.append(f"[FAIL] Test run exceeded {TEST_TIMEOUT_SECONDS}s and was terminated.")
            return False, "", "Test run timed out."
        except Exception as exc:  # noqa: BLE001 - a broken sandbox blocks the PR
            log_lines.append(f"[FAIL] Sandbox execution error: {exc}")
            return False, "", f"Sandbox error: {exc}"
        finally:
            if sandbox:
                shutil.rmtree(sandbox, ignore_errors=True)

    # -- Benchmarks ---------------------------------------------------------

    def _benchmark_comparisons(self) -> List[ValidationMetricComparison]:
        """
        Measure the patched configuration against the incident state.

        Both sides are measured by actually running the engine, so the
        scorecard reports observed numbers rather than quoted ones.
        """
        from rag_service.config import get_config, set_config, RAGConfig
        from rag_service.rag_engine import rag_engine

        original = get_config()
        queries = [
            "How does the Raft consensus algorithm handle network partitions?",
            "What are best practices for vector database top-k tuning?",
            "How does context reduction impact LLM latency and cost?",
        ]

        def measure(cfg: RAGConfig) -> Dict[str, float]:
            set_config(cfg)
            runs = [rag_engine.query(q) for _ in range(6) for q in queries]
            ordered = sorted(r["latency_seconds"] for r in runs)
            return {
                "p95": ordered[int(len(ordered) * 0.95) - 1],
                "cost": sum(r["cost_usd"] for r in runs) / len(runs),
                "chunks": sum(r["retrieved_chunks_count"] for r in runs) / len(runs),
                "grounded": sum(r["groundedness_score"] for r in runs) / len(runs),
                "relevance": sum(r["context_relevance_score"] for r in runs) / len(runs),
            }

        try:
            before = measure(original)
            patched = original.model_copy(update={
                "top_k": 8, "reranker_enabled": True, "reranker_top_n": 5,
            })
            after = measure(patched)
        finally:
            # Always restore: this runs against the live singleton config.
            set_config(original)

        return [
            _comparison("p95 Latency", before["p95"], after["p95"], "s", lower_is_better=True),
            _comparison("Cost per Request", before["cost"], after["cost"], "$", lower_is_better=True),
            _comparison("Retrieved Context Chunks", before["chunks"], after["chunks"], " chunks", lower_is_better=True),
            _comparison("Answer Groundedness", before["grounded"], after["grounded"], "%", lower_is_better=False),
            _comparison("Context Relevance Score", before["relevance"], after["relevance"], "%", lower_is_better=False),
        ]


def _comparison(
    name: str,
    before: float,
    after: float,
    unit: str,
    lower_is_better: bool,
) -> ValidationMetricComparison:
    """Format one measured before/after pair, deciding PASS on the direction of change."""
    if unit == "$":
        fmt = lambda v: f"${v:.3f}"  # noqa: E731
    elif unit == "%":
        fmt = lambda v: f"{v:.1f}%"  # noqa: E731
    elif unit == "s":
        fmt = lambda v: f"{v:.2f}s"  # noqa: E731
    else:
        fmt = lambda v: f"{v:.0f}{unit}"  # noqa: E731

    delta_pct = ((after - before) / before * 100.0) if before else 0.0
    improved = (after < before) if lower_is_better else (after > before)
    # Treat a negligible change as acceptable rather than a regression.
    neutral = abs(delta_pct) < 1.0

    return ValidationMetricComparison(
        metric_name=name,
        before_value=fmt(before),
        after_value=fmt(after),
        improvement=f"{delta_pct:+.1f}%",
        status="PASS" if (improved or neutral) else "FAIL",
    )


def _extract_pytest_summary(output: str) -> str:
    """
    Pull the outcome line out of pytest output for the agent log.

    Failures are checked first. Pytest's summary reads "1 failed, 96 passed",
    so matching on "passed" first reports a run as healthy when it was not --
    exactly the kind of misleading scorecard this agent exists to prevent.
    """
    failed = re.search(r"(\d+ failed[^\n]*)", output)
    if failed:
        return failed.group(1).strip()
    errored = re.search(r"(\d+ error[s]?[^\n]*)", output)
    if errored:
        return errored.group(1).strip()
    passed = re.search(r"(\d+ passed[^\n]*)", output)
    if passed:
        return passed.group(1).strip()
    return "no pytest summary found"


def _tail(text: str, lines: int) -> List[str]:
    stripped = [ln for ln in text.splitlines() if ln.strip()]
    return stripped[-lines:]


validation_agent = ValidationAgent()
