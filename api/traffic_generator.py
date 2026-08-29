"""
Synthetic Production Traffic Generator
Simulates a live stream of realistic user queries hitting the RAG application.
"""
import asyncio
import random
import time
from rag_service.rag_engine import rag_engine
from observability.metrics_collector import metrics_collector
from observability.anomaly_detector import anomaly_detector

SAMPLE_QUERIES = [
    "How does the Raft consensus algorithm handle network partitions?",
    "What are the best practices for vector database top-k retrieval tuning?",
    "Explain how to evaluate RAG systems using the RAG triad framework.",
    "What are the safety trade-offs of automated incident remediation in production?",
    "How does context token reduction impact LLM p95 latency and cost?",
    "What causes CPU throttling in Kubernetes pods under high request volume?",
    "Explain the difference between bi-encoders and cross-encoder rerankers.",
    "How can OpenTelemetry distributed tracing identify vector search bottlenecks?"
]

class TrafficGenerator:
    def __init__(self):
        self.running = False
        self._task = None

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()

    async def _run_loop(self):
        while self.running:
            try:
                query = random.choice(SAMPLE_QUERIES)
                # Execute RAG query
                result = rag_engine.query(query)
                # Record to telemetry
                metrics_collector.record_query_event(result)
                await asyncio.sleep(random.uniform(0.8, 1.8))
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[TrafficGenerator] Error: {e}")
                await asyncio.sleep(1.0)

traffic_generator = TrafficGenerator()
