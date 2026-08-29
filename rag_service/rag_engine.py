"""
RAG Engine Execution Pipeline
Performs dense retrieval, semantic reranking, prompt assembly, and response generation with telemetry instrumentation.
"""
import time
import random
import numpy as np
from typing import Dict, Any, List
from rag_service.config import get_config, RAGConfig
from rag_service.knowledge_base import DOCUMENTS, _compute_mock_embedding

# --- Simulation constants -------------------------------------------------
# Calibrated so the modelled service reproduces the documented incident
# envelope for INC-2026-0042, and so the healthy baseline sits comfortably
# below the anomaly detector's firing threshold rather than on top of it:
#
#                     p95 latency     cost/request     prompt tokens
#   Healthy           ~2.1s           ~$0.03           ~2,710
#   Incident          ~11.8s          ~$0.14           ~15,510
#   Remediated        ~2.1s           ~$0.03           ~2,048 (bounded)
#
# Covered by tests/test_rag_pipeline.py::test_incident_envelope_matches_docs.
ATTENTION_LINEAR_COEFF = 0.000098      # per-token decode cost
ATTENTION_QUADRATIC_COEFF = 3.19e-8    # O(n^2) self-attention over the prompt
PRICING_SCALE = 46.4                   # blended per-request premium
PER_CHUNK_COST_USD = 0.00084           # retrieval I/O per context chunk


class RAGEngine:
    def __init__(self):
        pass

    def query(self, user_query: str) -> Dict[str, Any]:
        """
        Executes the full RAG query pipeline and records execution telemetry.
        """
        cfg = get_config()
        start_time = time.time()
        
        # 1. Query Embedding
        query_words = [w.lower().strip() for w in user_query.split()]
        query_vec = _compute_mock_embedding(user_query, query_words)
        
        # 2. Vector Retrieval (Cosine Similarity)
        scored_docs = []
        for doc in DOCUMENTS:
            doc_vec = doc["embedding"]
            sim = float(np.dot(query_vec, doc_vec))
            for w in query_words:
                if w in doc["keywords"] or w in doc["content"].lower():
                    sim += 0.35
            scored_docs.append((sim, doc))
        
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        
        retrieved_items = []
        for i in range(cfg.top_k):
            base_sim, doc = scored_docs[i % len(scored_docs)]
            noisy_sim = max(0.1, base_sim - (i * 0.015))
            chunk_copy = dict(doc)
            chunk_copy["chunk_id"] = f"{doc['id']}_chunk_{i+1}"
            chunk_copy["similarity_score"] = round(noisy_sim, 3)
            retrieved_items.append(chunk_copy)
        
        # 3. Optional Reranking Stage
        final_context_docs = retrieved_items
        rerank_applied = False
        if cfg.reranker_enabled and len(retrieved_items) > cfg.reranker_top_n:
            rerank_applied = True
            scored_rerank = []
            for item in retrieved_items:
                relevance_boost = 0.3 if any(w in item["keywords"] for w in query_words) else 0.0
                rerank_score = item["similarity_score"] + relevance_boost
                scored_rerank.append((rerank_score, item))
            scored_rerank.sort(key=lambda x: x[0], reverse=True)
            final_context_docs = [item for _, item in scored_rerank[:cfg.reranker_top_n]]

        # 4. Context assembly and token calculation
        chunk_count = len(final_context_docs)
        prompt_tokens = 150 + (chunk_count * cfg.chunk_size)

        # The context bound is only actually enforced when the reranker is
        # selecting a bounded candidate set. Without reranking, every retrieved
        # chunk lands in the prompt unbounded — which is precisely the failure
        # mode INC-2026-0042 models. Clamping unconditionally here would flatten
        # the incident and the healthy baseline to the same token count and the
        # blowout could never occur.
        if cfg.reranker_enabled:
            prompt_tokens = min(prompt_tokens, cfg.max_context_tokens)

        output_tokens = min(cfg.max_output_tokens, 200 + random.randint(20, 80))
        total_tokens = prompt_tokens + output_tokens

        # 5. Cost modeling
        # Token rates are per-token list prices; PRICING_SCALE expresses the
        # blended per-request premium (vector search + eval passes), and the
        # per-chunk term covers retrieval I/O that scales with context volume.
        cost_usd = (prompt_tokens * 0.00000015) + (output_tokens * 0.00000060)
        cost_usd = round((cost_usd * PRICING_SCALE) + (chunk_count * PER_CHUNK_COST_USD), 4)

        # 6. Latency modeling
        # Generation cost is quadratic in prompt length: self-attention is
        # O(n^2) in sequence length, which is why context bloat degrades latency
        # far faster than it grows the prompt. At the healthy baseline (~2.7k
        # tokens) the quadratic term is minor; at incident volume (~15.5k
        # tokens) it dominates and drives p95 past 11s.
        base_latency = 1.2
        retrieval_latency = 0.04 * cfg.top_k
        rerank_latency = 0.12 if rerank_applied else 0.0
        generation_latency = (
            0.1
            + (prompt_tokens * ATTENTION_LINEAR_COEFF)
            + (prompt_tokens ** 2 * ATTENTION_QUADRATIC_COEFF)
        )

        simulated_duration = base_latency + retrieval_latency + rerank_latency + generation_latency
        simulated_duration += random.uniform(-0.10, 0.15)
        simulated_duration = max(0.5, round(simulated_duration, 2))
        
        # 7. Triad Evaluation Scores
        if chunk_count <= 5:
            groundedness = random.uniform(93.0, 97.0)
            context_relevance = random.uniform(91.0, 96.0)
            answer_quality = random.uniform(92.0, 98.0)
        elif chunk_count <= 10:
            groundedness = random.uniform(88.0, 93.0)
            context_relevance = random.uniform(85.0, 91.0)
            answer_quality = random.uniform(87.0, 93.0)
        else:
            groundedness = random.uniform(78.0, 84.0)
            context_relevance = random.uniform(62.0, 74.0)
            answer_quality = random.uniform(80.0, 85.0)
        
        top_doc = final_context_docs[0] if final_context_docs else {"title": "General Knowledge", "content": "No context found."}
        answer_text = f"Based on {top_doc['title']}: {top_doc['content'][:180]}... The system evaluated {chunk_count} context chunks to formulate this response."
        
        return {
            "query": user_query,
            "answer": answer_text,
            "latency_seconds": simulated_duration,
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost_usd,
            "retrieved_chunks_count": chunk_count,
            "top_k_configured": cfg.top_k,
            "reranker_enabled": cfg.reranker_enabled,
            "groundedness_score": round(groundedness, 1),
            "context_relevance_score": round(context_relevance, 1),
            "answer_quality_score": round(answer_quality, 1),
            "sources": [{"id": d["id"], "title": d["title"]} for d in final_context_docs[:4]],
            "timestamp": time.time()
        }

rag_engine = RAGEngine()
