"""
Unit tests for RAG pipeline and configuration bounds.
"""
import pytest
from rag_service.config import get_config, set_config, RAGConfig, reset_to_healthy_baseline
from rag_service.rag_engine import rag_engine

def test_rag_baseline_execution():
    reset_to_healthy_baseline()
    res = rag_engine.query("Explain Raft consensus protocol")
    assert "answer" in res
    assert res["retrieved_chunks_count"] <= 5
    assert res["latency_seconds"] < 4.0
    assert res["groundedness_score"] >= 90.0

def test_top_k_bounds():
    with pytest.raises(Exception):
        RAGConfig(top_k=100) # Exceeds max bounds

def test_reranker_configuration():
    reset_to_healthy_baseline()
    cfg = get_config()
    cfg.reranker_enabled = True
    cfg.top_k = 10
    cfg.reranker_top_n = 5
    res = rag_engine.query("vector search indexing")
    assert res["retrieved_chunks_count"] == 5
    assert res["reranker_enabled"] is True


# --------------------------------------------------------------------------
# Incident envelope
#
# The numbers below are quoted throughout the README, ARCHITECTURE, the
# generated PR body, and the diagnosis agent's narrative. If the simulation
# drifts away from them the documentation silently becomes fiction, so the
# envelope is pinned here.
# --------------------------------------------------------------------------

def _p95(samples):
    ordered = sorted(samples)
    return ordered[int(len(ordered) * 0.95) - 1]


def _measure(n=40):
    results = [rag_engine.query("how does raft handle leader partition") for _ in range(n)]
    return {
        "p95": _p95([r["latency_seconds"] for r in results]),
        "cost": sum(r["cost_usd"] for r in results) / len(results),
        "prompt_tokens": sum(r["prompt_tokens"] for r in results) / len(results),
        "chunks": sum(r["retrieved_chunks_count"] for r in results) / len(results),
    }


def test_incident_envelope_matches_docs():
    """Healthy -> incident -> remediated must reproduce the documented figures."""
    from rag_service.chaos_injector import inject_scenario, clear_chaos
    from rag_service.config import update_config_fields

    clear_chaos()
    healthy = _measure()
    assert 1.8 <= healthy["p95"] <= 2.5, f"healthy p95 drifted: {healthy['p95']}"
    assert 0.025 <= healthy["cost"] <= 0.035, f"healthy cost drifted: {healthy['cost']}"

    inject_scenario("retriever_latency_spike")
    incident = _measure()
    assert 10.5 <= incident["p95"] <= 13.0, f"incident p95 drifted: {incident['p95']}"
    assert 0.12 <= incident["cost"] <= 0.16, f"incident cost drifted: {incident['cost']}"
    assert incident["chunks"] == 30

    clear_chaos()
    update_config_fields(top_k=8, reranker_enabled=True, reranker_top_n=5)
    remediated = _measure()
    assert remediated["p95"] < 3.0, f"remediation did not restore latency: {remediated['p95']}"
    assert remediated["cost"] < 0.05
    clear_chaos()


def test_context_blowout_actually_occurs_during_the_incident():
    """
    The documented root cause is prompt token bloat.

    An unconditional context clamp would flatten the incident and the baseline
    to the same token count, leaving the narrative describing a mechanism the
    code never exercises.
    """
    from rag_service.chaos_injector import inject_scenario, clear_chaos

    clear_chaos()
    healthy_tokens = rag_engine.query("raft consensus")["prompt_tokens"]

    inject_scenario("retriever_latency_spike")
    incident_tokens = rag_engine.query("raft consensus")["prompt_tokens"]
    clear_chaos()

    assert incident_tokens > healthy_tokens * 4, (
        f"context did not blow up: {healthy_tokens} -> {incident_tokens}"
    )
    # The PR body quotes ~15,500 tokens.
    assert 14_000 <= incident_tokens <= 17_000


def test_healthy_baseline_stays_below_the_detector_threshold():
    """
    A healthy baseline above the firing threshold would page on every request.
    """
    from observability.anomaly_detector import anomaly_detector
    from rag_service.chaos_injector import clear_chaos

    clear_chaos()
    healthy = _measure()
    threshold = anomaly_detector.baseline["p95_latency"] * 1.5
    assert healthy["p95"] < threshold, (
        f"healthy p95 {healthy['p95']:.2f}s exceeds detector threshold {threshold:.2f}s"
    )


def test_reranker_enforces_the_context_bound():
    """With reranking on, the prompt must respect max_context_tokens."""
    from rag_service.chaos_injector import clear_chaos
    from rag_service.config import update_config_fields

    clear_chaos()
    cfg = update_config_fields(top_k=8, reranker_enabled=True, reranker_top_n=5)
    res = rag_engine.query("vector database indexing best practices")
    assert res["prompt_tokens"] <= cfg.max_context_tokens
    clear_chaos()


def test_clearing_chaos_restores_the_healthy_config():
    """
    Reset must restore the runtime config, not just the banner.

    Clearing only the marker would report a healthy system while the injected
    mutation continued to degrade every request.
    """
    from rag_service.chaos_injector import inject_scenario, clear_chaos, get_active_chaos

    inject_scenario("retriever_latency_spike")
    assert get_config().top_k == 30

    clear_chaos()
    assert get_active_chaos() is None
    assert get_config().top_k == 5, "reset left the injected fault active"
    assert get_config().similarity_threshold == 0.68
