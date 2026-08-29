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
