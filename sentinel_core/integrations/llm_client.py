"""
LLM-Backed Diagnosis

The Diagnosis Agent is the one stage of the pipeline where a language model
earns its place: root-cause analysis is open-ended, the evidence is
heterogeneous, and the answer cannot be enumerated in advance. Every other
stage (detection thresholds, patch application, test execution) is
deterministic work that code does better and cheaper.

Two implementations behind one interface:

  * `AnthropicDiagnosisAgent` gives Claude a set of investigation tools and
    lets it decide what to look at. It is a genuine agentic loop, not a single
    templated call: the model queries metrics, reads the live retrieval
    config, pulls the change history, and searches the operational runbooks,
    then submits a structured verdict.
  * `DeterministicDiagnosisClient` reproduces the shipped incident's analysis
    with no network call, so the demo and the test suite run without an API
    key or a cent of spend.

Selection is by configuration, matching the GitHub client pattern: a missing
key degrades to the deterministic path rather than breaking the incident
pipeline.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger("sentinel.llm")


class LLMError(RuntimeError):
    """Raised when the model call fails or returns an unusable result."""


@dataclass
class DiagnosisContext:
    """Everything the diagnosing agent is allowed to look at."""
    incident_id: str
    title: str
    severity: str
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    metrics_snapshot: Dict[str, Any] = field(default_factory=dict)
    baseline: Dict[str, Any] = field(default_factory=dict)
    active_config: Dict[str, Any] = field(default_factory=dict)
    config_history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DiagnosisResult:
    """A structured root-cause verdict."""
    root_cause_title: str
    root_cause_summary: str
    confidence: float
    evidence_items: List[str]
    suspect_file: str = "rag_service/config.py"
    suspect_changes: Dict[str, Any] = field(default_factory=dict)
    # What the agent actually did to reach the verdict. Surfaced in the UI so
    # a reviewer can audit the reasoning path, not just the conclusion.
    investigation_log: List[str] = field(default_factory=list)
    model: str = "deterministic"
    llm_backed: bool = False


@runtime_checkable
class DiagnosisClient(Protocol):
    def diagnose(self, context: DiagnosisContext) -> DiagnosisResult:
        ...


# --------------------------------------------------------------------------
# Deterministic fallback
# --------------------------------------------------------------------------

class DeterministicDiagnosisClient:
    """
    Rule-based analysis of the shipped incident. No network, no API key.

    Kept as a first-class implementation rather than dead code: it is what
    runs in CI, and it is the graceful-degradation path when the model is
    unreachable mid-incident.
    """

    def diagnose(self, context: DiagnosisContext) -> DiagnosisResult:
        cfg = context.active_config
        top_k = cfg.get("top_k", 30)
        chunk_size = cfg.get("chunk_size", 512)
        reranker = cfg.get("reranker_enabled", False)
        estimated_tokens = 150 + (top_k * chunk_size)

        return DiagnosisResult(
            root_cause_title="Retrieval Top-K Misconfiguration Causing Context Window Saturation",
            root_cause_summary=(
                f"The retriever is configured with top_k={top_k} and reranking "
                f"{'enabled' if reranker else 'disabled'}. Every request therefore assembles "
                f"approximately {estimated_tokens:,} prompt tokens of context. Self-attention "
                f"cost grows quadratically with sequence length, so the oversized context "
                f"degrades latency far faster than it grows the prompt, while the additional "
                f"low-relevance chunks dilute grounding and reduce answer quality."
            ),
            confidence=0.92,
            evidence_items=[
                f"Active retrieval configuration reports top_k={top_k} against a baseline of 5.",
                f"Reranking is {'enabled' if reranker else 'disabled'}, so no stage bounds the context.",
                f"Estimated prompt size is ~{estimated_tokens:,} tokens per request.",
                "Latency, cost, and retrieval volume rose together while groundedness fell, "
                "which is the signature of context dilution rather than infrastructure load.",
            ],
            suspect_file="rag_service/config.py",
            suspect_changes={"top_k": top_k, "reranker_enabled": reranker},
            investigation_log=["Applied deterministic rule set (no model call)."],
            model="deterministic",
            llm_backed=False,
        )


# --------------------------------------------------------------------------
# Claude-backed agent
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the diagnosis agent inside SentinelAI, an autonomous \
reliability platform for production RAG and agentic AI services.

An incident has been detected. Your job is to determine the root cause and \
submit a structured verdict.

You have tools that read the live system. Use them - do not speculate from the \
incident summary alone. A useful investigation typically:
  - reads the current metrics against the healthy baseline
  - reads the active retrieval configuration
  - checks what recently changed
  - consults the operational runbooks for the failure signature you are seeing

Reason about mechanism, not correlation. "Latency rose" is an observation; \
"top_k=30 without reranking put ~15,500 tokens in every prompt, and attention \
cost is quadratic in sequence length" is a root cause.

Set your confidence honestly. Reserve values above 0.9 for cases where you \
identified a specific configuration value and can explain the causal chain \
from that value to every anomaly observed. If the evidence is ambiguous, say \
so with a lower confidence and name what you could not rule out.

When you have enough evidence, call submit_diagnosis exactly once."""


class AnthropicDiagnosisAgent:
    """
    Root-cause analysis via Claude with investigation tools.

    The model drives the loop: it chooses which tools to call and when it has
    seen enough. The tools are read-only by construction -- this agent can
    inspect the system but cannot change it, which keeps the blast radius of a
    model mistake at "wrong explanation" rather than "wrong mutation".
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-opus-5",
        effort: str = "high",
        max_tokens: int = 8000,
        knowledge_lookup=None,
    ):
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self._api_key = api_key
        self._knowledge_lookup = knowledge_lookup

    def _client(self):
        # Imported lazily so the package imports cleanly without the SDK
        # installed and without an API key present.
        import anthropic

        if self._api_key:
            return anthropic.Anthropic(api_key=self._api_key)
        # No explicit key: let the SDK resolve credentials from the
        # environment or a configured profile.
        return anthropic.Anthropic()

    def diagnose(self, context: DiagnosisContext) -> DiagnosisResult:
        try:
            from anthropic import beta_tool
        except ImportError as exc:
            raise LLMError(
                "the 'anthropic' package is required for LLM-backed diagnosis"
            ) from exc

        client = self._client()

        # Captured by the tools below; populated when the model submits.
        verdict: Dict[str, Any] = {}
        investigation: List[str] = []

        @beta_tool
        def get_metrics_snapshot() -> str:
            """Read current service metrics alongside the healthy baseline.

            Returns p50/p95/p99 latency, cost per request, average retrieved
            chunk count, and RAG Triad quality scores, with the baseline each
            is being compared against.
            """
            investigation.append("Read current metrics against baseline")
            return json.dumps({
                "current": context.metrics_snapshot,
                "healthy_baseline": context.baseline,
                "detected_anomalies": context.anomalies,
            }, indent=2)

        @beta_tool
        def get_retrieval_config() -> str:
            """Read the live retrieval and inference configuration.

            Includes top_k, similarity threshold, reranker settings, chunk
            size, and context window bounds currently in effect.
            """
            investigation.append("Read active retrieval configuration")
            return json.dumps(context.active_config, indent=2)

        @beta_tool
        def get_recent_changes() -> str:
            """List recent configuration changes, newest first.

            Use this to correlate the incident's start time with a specific
            change to the service.
            """
            investigation.append("Reviewed recent configuration change history")
            if not context.config_history:
                return "No configuration change records available for this window."
            return json.dumps(context.config_history, indent=2)

        @beta_tool
        def search_runbooks(query: str) -> str:
            """Search the operational knowledge base and incident runbooks.

            Args:
                query: What to look for, e.g. "context window latency" or
                    "retrieval volume cost".
            """
            investigation.append(f"Searched runbooks for: {query}")
            if self._knowledge_lookup is None:
                return "Knowledge base unavailable."
            try:
                hits = self._knowledge_lookup(query)
            except Exception as exc:  # noqa: BLE001 - a tool failure is data, not a crash
                return f"Knowledge base lookup failed: {exc}"
            if not hits:
                return f"No runbook entries matched {query!r}."
            return json.dumps(hits, indent=2)

        @beta_tool
        def submit_diagnosis(
            root_cause_title: str,
            root_cause_summary: str,
            confidence: float,
            evidence_items: List[str],
            suspect_file: str,
            suspect_changes: str,
        ) -> str:
            """Submit the final root-cause verdict. Call this exactly once.

            Args:
                root_cause_title: Short noun phrase naming the root cause.
                root_cause_summary: Two to four sentences explaining the causal
                    mechanism from the configuration value to the observed
                    anomalies.
                confidence: 0.0 to 1.0. Above 0.9 only when a specific value is
                    identified and the full causal chain is explained.
                evidence_items: Specific observations supporting the verdict,
                    each citing a concrete value you read from a tool.
                suspect_file: Repository path of the file believed responsible.
                suspect_changes: JSON object of the specific parameters and
                    values implicated, e.g. {"top_k": 30}.
            """
            verdict.update({
                "root_cause_title": root_cause_title,
                "root_cause_summary": root_cause_summary,
                "confidence": confidence,
                "evidence_items": evidence_items,
                "suspect_file": suspect_file,
                "suspect_changes": suspect_changes,
            })
            return "Diagnosis recorded."

        user_prompt = (
            f"Incident {context.incident_id} has been detected.\n\n"
            f"Title: {context.title}\n"
            f"Severity: {context.severity}\n\n"
            f"Correlated anomalies:\n{json.dumps(context.anomalies, indent=2)}\n\n"
            f"Investigate and submit your verdict."
        )

        try:
            runner = client.beta.messages.tool_runner(
                model=self.model,
                max_tokens=self.max_tokens,
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
                system=SYSTEM_PROMPT,
                tools=[
                    get_metrics_snapshot,
                    get_retrieval_config,
                    get_recent_changes,
                    search_runbooks,
                    submit_diagnosis,
                ],
                messages=[{"role": "user", "content": user_prompt}],
            )
            for _message in runner:
                # The runner drives tool execution; the closures above record
                # both the investigation trail and the final verdict.
                pass
        except Exception as exc:  # noqa: BLE001 - normalized for the caller
            raise LLMError(f"diagnosis model call failed: {exc}") from exc

        if not verdict:
            raise LLMError("the model completed without submitting a diagnosis")

        return DiagnosisResult(
            root_cause_title=verdict["root_cause_title"],
            root_cause_summary=verdict["root_cause_summary"],
            confidence=_clamp_confidence(verdict.get("confidence", 0.8)),
            evidence_items=list(verdict.get("evidence_items") or []),
            suspect_file=verdict.get("suspect_file") or "rag_service/config.py",
            suspect_changes=_coerce_changes(verdict.get("suspect_changes")),
            investigation_log=investigation,
            model=self.model,
            llm_backed=True,
        )


def _clamp_confidence(value: Any) -> float:
    """Keep confidence inside the range DiagnosisReport accepts."""
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.8


def _coerce_changes(raw: Any) -> Dict[str, Any]:
    """
    Accept either a JSON string or an object for suspect_changes.

    The parameter is typed as a string so the tool schema stays flat, but
    models reasonably return a real object sometimes. Rejecting that would
    discard a correct diagnosis over a formatting detail.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return {"note": raw}
    return {}


def build_diagnosis_client(settings=None) -> DiagnosisClient:
    """
    Select a diagnosis implementation from deployment settings.

    Falls back to deterministic analysis when the LLM is disabled or
    unconfigured, so an incident is never lost to a missing API key.
    """
    if settings is None:
        from sentinel_core.settings import settings as default_settings
        settings = default_settings

    llm = settings.llm
    if not llm.is_configured:
        return DeterministicDiagnosisClient()

    def knowledge_lookup(query: str):
        from rag_service.knowledge_base import DOCUMENTS
        terms = [t for t in query.lower().split() if len(t) > 2]
        hits = []
        for doc in DOCUMENTS:
            haystack = f"{doc['title']} {doc['content']} {' '.join(doc.get('keywords', []))}".lower()
            if any(term in haystack for term in terms):
                hits.append({"title": doc["title"], "content": doc["content"][:600]})
        return hits[:4]

    return AnthropicDiagnosisAgent(
        api_key=llm.api_key,
        model=llm.model,
        effort=llm.effort,
        max_tokens=llm.max_tokens,
        knowledge_lookup=knowledge_lookup,
    )
