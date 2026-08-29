"""
Anomaly Detection & Incident Trigger Engine
Monitors live telemetry against healthy statistical baselines and emits structured Incidents.
"""
import time
from typing import Dict, Any, List, Optional
from observability.metrics_collector import metrics_collector

class AnomalyDetector:
    def __init__(self):
        self.baseline = {
            "p95_latency": 2.1,
            "avg_cost_usd": 0.030,
            "avg_chunks": 5.0,
            "avg_groundedness": 94.0,
            "avg_quality": 93.0,
            "error_rate": 0.0
        }
        self.incident_counter = 42

    def check_for_anomalies(self) -> Optional[Dict[str, Any]]:
        """
        Evaluates current metrics against baseline thresholds.
        Returns an incident payload if an anomaly is detected.
        """
        current = metrics_collector.get_current_metrics()
        if not current:
            return None

        anomalies = []

        # 1. Check Latency Spikes
        curr_p95 = current.get("p95_latency", 2.1)
        lat_ratio = curr_p95 / self.baseline["p95_latency"]
        if lat_ratio >= 1.5:
            lat_pct = int((lat_ratio - 1.0) * 100)
            sev = "HIGH" if lat_ratio >= 2.0 else "MEDIUM"
            anomalies.append({
                "metric": "p95_latency",
                "title": "p95 Latency Spike",
                "baseline": f"{self.baseline['p95_latency']}s",
                "current": f"{curr_p95}s",
                "change_pct": f"+{lat_pct}%",
                "severity": sev
            })

        # 2. Check Cost/Request Blowout
        curr_cost = current.get("avg_cost_usd", 0.03)
        cost_ratio = curr_cost / self.baseline["avg_cost_usd"]
        if cost_ratio >= 1.5:
            cost_pct = int((cost_ratio - 1.0) * 100)
            sev = "HIGH" if cost_ratio >= 2.0 else "MEDIUM"
            anomalies.append({
                "metric": "cost_per_request",
                "title": "Cost Per Request Escalation",
                "baseline": f"${self.baseline['avg_cost_usd']:.2f}",
                "current": f"${curr_cost:.2f}",
                "change_pct": f"+{cost_pct}%",
                "severity": sev
            })

        # 3. Check Retrieval Volume Explosion
        curr_chunks = current.get("avg_chunks", 5.0)
        chunk_ratio = curr_chunks / self.baseline["avg_chunks"]
        if chunk_ratio >= 1.5:
            chunk_pct = int((chunk_ratio - 1.0) * 100)
            sev = "HIGH" if chunk_ratio >= 2.0 else "MEDIUM"
            anomalies.append({
                "metric": "retrieval_chunks",
                "title": "Excessive Retrieval Volume",
                "baseline": f"{int(self.baseline['avg_chunks'])} chunks",
                "current": f"{int(curr_chunks)} chunks",
                "change_pct": f"+{chunk_pct}%",
                "severity": sev
            })

        # 4. Check Answer Quality & Groundedness Degradation
        curr_groundedness = current.get("avg_groundedness", 94.0)
        if curr_groundedness < 88.0:
            drop_pct = int(self.baseline["avg_groundedness"] - curr_groundedness)
            sev = "HIGH" if curr_groundedness < 80.0 else "MEDIUM"
            anomalies.append({
                "metric": "groundedness_score",
                "title": "Hallucination Drift / Groundedness Drop",
                "baseline": f"{self.baseline['avg_groundedness']}%",
                "current": f"{curr_groundedness}%",
                "change_pct": f"-{drop_pct}%",
                "severity": sev
            })

        if not anomalies:
            return None

        overall_severity = "HIGH" if any(a["severity"] == "HIGH" for a in anomalies) else ("MEDIUM" if any(a["severity"] == "MEDIUM" for a in anomalies) else "LOW")

        # Build Incident Payload
        inc_id = f"INC-2026-00{self.incident_counter:02d}"
        return {
            "incident_id": inc_id,
            "timestamp": time.time(),
            "severity": overall_severity,
            "status": "DETECTED",
            "title": f"High Severity RAG Incident: Latency & Cost Surge ({inc_id})",
            "anomalies": anomalies,
            "current_metrics_snapshot": current,
            "baseline_snapshot": self.baseline
        }

anomaly_detector = AnomalyDetector()
