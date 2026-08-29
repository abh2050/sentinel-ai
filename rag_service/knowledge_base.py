"""
Enterprise Knowledge Base & Vector Store Simulator
Provides indexed documents on Cloud Infrastructure, SRE incident management, and AI reliability.
"""
import os
import json
import numpy as np
from typing import List, Dict, Any

DEFAULT_DOCUMENTS = [
    {
        "id": "doc-001",
        "title": "Distributed Consensus & Raft Protocol",
        "content": "The Raft consensus algorithm guarantees state machine replication across a distributed cluster by electing a distinguished leader, maintaining replicated logs, and ensuring safety through majority quorum commits.",
        "category": "infrastructure",
        "keywords": ["raft", "consensus", "distributed", "quorum", "leader election", "replication"]
    },
    {
        "id": "doc-002",
        "title": "Vector Database Indexing & HNSW Top-K Tuning",
        "content": "Hierarchical Navigable Small World (HNSW) graphs offer logarithmic search complexity. Increasing top_k retrieval past 10 without semantic reranking creates severe prompt bloat, increases quadratic attention cost in LLMs, and degrades answer groundedness.",
        "category": "ai_infrastructure",
        "keywords": ["vector", "hnsw", "top_k", "retrieval", "reranking", "index", "latency"]
    },
    {
        "id": "doc-003",
        "title": "Production RAG Reliability & Triad Evaluations",
        "content": "Evaluating RAG systems requires measuring the RAG Triad: Context Relevance (precision of retrieved chunks), Groundedness / Faithfulness (absence of hallucinations in LLM output), and Answer Relevance (directness of response to query).",
        "category": "ai_evaluation",
        "keywords": ["rag", "triad", "groundedness", "hallucination", "context relevance", "eval"]
    },
    {
        "id": "doc-004",
        "title": "SRE Incident Management & Automated Remediation",
        "content": "Automated incident remediation workflows must maintain strict human-in-the-loop governance. While AI agents can triage, diagnose, and create pull requests, automated merges to production without human authorization introduce catastrophic operational risk.",
        "category": "sre",
        "keywords": ["incident", "sre", "remediation", "pr", "human-in-the-loop", "governance", "safety"]
    },
    {
        "id": "doc-005",
        "title": "LLM Token Economics & Cost Optimization",
        "content": "Prompt tokens dominate RAG cost profiles. Reducing retrieved chunk volume from 30 chunks (12,000 tokens) to 5 chunks (2,000 tokens) decreases per-query cost by over 75% while simultaneously reducing time-to-first-token (TTFT) and p95 latency.",
        "category": "cost_engineering",
        "keywords": ["cost", "tokens", "pricing", "latency", "ttft", "prompt", "optimization"]
    },
    {
        "id": "doc-006",
        "title": "Kubernetes Pod Autoscaling & Throttling Limits",
        "content": "CPU throttling occurs when CFS quotas are misconfigured on container workloads. Horizontal Pod Autoscalers (HPA) should scale on custom metrics including request queue depth and p95 latency rather than raw CPU utilization.",
        "category": "kubernetes",
        "keywords": ["kubernetes", "k8s", "hpa", "scaling", "throttling", "cfs", "cpu"]
    },
    {
        "id": "doc-007",
        "title": "Semantic Reranking Architecture (Flash-Reranker)",
        "content": "Two-stage retrieval pipelines retrieve top-20 candidates using dense bi-encoders, followed by a fast cross-encoder reranker that scores relevance and passes the top-5 most relevant chunks to the generator. This maximizes precision while bounding context size.",
        "category": "ai_infrastructure",
        "keywords": ["reranking", "reranker", "cross-encoder", "bi-encoder", "precision", "top_n"]
    },
    {
        "id": "doc-008",
        "title": "OpenTelemetry Distributed Tracing in AI Pipelines",
        "content": "OpenTelemetry spans capture the lifecycle of AI requests across retrieval latency, vector DB query time, token generation spans, and evaluation guardrails. Spans enable precise anomaly attribution during incidents.",
        "category": "observability",
        "keywords": ["opentelemetry", "tracing", "spans", "telemetry", "metrics", "observability"]
    }
]

def _compute_mock_embedding(text: str, keywords: List[str]) -> np.ndarray:
    np.random.seed(abs(hash(text[:30])) % (2**31))
    vec = np.random.randn(64)
    for kw in keywords:
        kw_hash = abs(hash(kw)) % 64
        vec[kw_hash] += 2.5
    norm = np.linalg.norm(vec)
    return vec / (norm + 1e-8)

def load_documents() -> List[Dict[str, Any]]:
    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge_corpus.json")
    if os.path.exists(data_path):
        try:
            with open(data_path, "r", encoding="utf-8") as f:
                docs = json.load(f)
                for doc in docs:
                    doc["embedding"] = _compute_mock_embedding(doc["content"], doc.get("keywords", []))
                return docs
        except Exception:
            pass
    
    # Fallback
    for doc in DEFAULT_DOCUMENTS:
        doc["embedding"] = _compute_mock_embedding(doc["content"], doc.get("keywords", []))
    return DEFAULT_DOCUMENTS

DOCUMENTS = load_documents()

def get_all_documents() -> List[Dict[str, Any]]:
    return DOCUMENTS
