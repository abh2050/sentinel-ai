"""
Observability & Real-Time Telemetry Collector
Maintains rolling window timeseries metrics, percentiles (p50/p95/p99), cost, tokens, and RAG quality evaluations.
"""
import time
import numpy as np
from collections import deque
from typing import Dict, Any, List

class MetricsCollector:
    def __init__(self, max_history: int = 120):
        self.max_history = max_history
        self.raw_records = deque(maxlen=max_history)
        self.timeseries_history = deque(maxlen=max_history)
        
        # Populate initial healthy baseline metrics
        self._seed_baseline_history()

    def _seed_baseline_history(self):
        now = time.time()
        for i in range(40):
            ts = now - ((40 - i) * 2.0)
            rec = {
                "latency_seconds": float(np.random.normal(2.1, 0.2)),
                "cost_usd": float(np.random.normal(0.031, 0.003)),
                "total_tokens": int(np.random.normal(1250, 100)),
                "retrieved_chunks_count": 5,
                "groundedness_score": float(np.random.normal(94.5, 1.5)),
                "context_relevance_score": float(np.random.normal(92.0, 2.0)),
                "answer_quality_score": float(np.random.normal(94.0, 1.8)),
                "error": False,
                "timestamp": ts
            }
            self.raw_records.append(rec)
            self._record_timeseries_snapshot(ts, rec)

    def record_query_event(self, event_data: Dict[str, Any]):
        """
        Records a telemetry event from a live RAG request.
        """
        ts = event_data.get("timestamp", time.time())
        rec = {
            "latency_seconds": event_data.get("latency_seconds", 2.0),
            "cost_usd": event_data.get("cost_usd", 0.03),
            "total_tokens": event_data.get("total_tokens", 1200),
            "retrieved_chunks_count": event_data.get("retrieved_chunks_count", 5),
            "groundedness_score": event_data.get("groundedness_score", 95.0),
            "context_relevance_score": event_data.get("context_relevance_score", 92.0),
            "answer_quality_score": event_data.get("answer_quality_score", 94.0),
            "error": event_data.get("error", False),
            "timestamp": ts
        }
        self.raw_records.append(rec)
        self._record_timeseries_snapshot(ts, rec)

    def _record_timeseries_snapshot(self, ts: float, latest_rec: Dict[str, Any]):
        recent = list(self.raw_records)[-20:]
        latencies = [r["latency_seconds"] for r in recent]
        costs = [r["cost_usd"] for r in recent]
        groundedness = [r["groundedness_score"] for r in recent]
        quality = [r["answer_quality_score"] for r in recent]
        chunks = [r["retrieved_chunks_count"] for r in recent]
        
        point = {
            "timestamp": ts,
            "time_formatted": time.strftime("%H:%M:%S", time.localtime(ts)),
            "p50_latency": round(float(np.percentile(latencies, 50)), 2),
            "p95_latency": round(float(np.percentile(latencies, 95)), 2),
            "p99_latency": round(float(np.percentile(latencies, 99)), 2),
            "avg_cost": round(float(np.mean(costs)), 4),
            "avg_groundedness": round(float(np.mean(groundedness)), 1),
            "avg_quality": round(float(np.mean(quality)), 1),
            "avg_chunks": round(float(np.mean(chunks)), 1),
            "latest_latency": round(latest_rec["latency_seconds"], 2),
            "latest_cost": round(latest_rec["cost_usd"], 4),
        }
        self.timeseries_history.append(point)

    def get_current_metrics(self) -> Dict[str, Any]:
        """
        Returns current aggregate metrics and timeseries buffer.
        """
        recent = list(self.raw_records)[-25:] if self.raw_records else []
        if not recent:
            return {}
            
        latencies = [r["latency_seconds"] for r in recent]
        costs = [r["cost_usd"] for r in recent]
        tokens = [r["total_tokens"] for r in recent]
        chunks = [r["retrieved_chunks_count"] for r in recent]
        groundedness = [r["groundedness_score"] for r in recent]
        quality = [r["answer_quality_score"] for r in recent]
        errors = [1 if r.get("error", False) else 0 for r in recent]
        
        return {
            "p50_latency": round(float(np.percentile(latencies, 50)), 2),
            "p95_latency": round(float(np.percentile(latencies, 95)), 2),
            "p99_latency": round(float(np.percentile(latencies, 99)), 2),
            "avg_cost_usd": round(float(np.mean(costs)), 4),
            "avg_tokens": int(np.mean(tokens)),
            "avg_chunks": round(float(np.mean(chunks)), 1),
            "avg_groundedness": round(float(np.mean(groundedness)), 1),
            "avg_quality": round(float(np.mean(quality)), 1),
            "error_rate": round(float(np.mean(errors)) * 100.0, 1),
            "sample_count": len(recent),
            "timeseries": list(self.timeseries_history)
        }

metrics_collector = MetricsCollector()
