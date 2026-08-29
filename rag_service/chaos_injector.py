"""
Chaos & Fault Injection Module
Simulates realistic production incidents for testing the autonomous reliability platform.
"""
from typing import Dict, Any
from rag_service.config import get_config, update_config_fields, reset_to_healthy_baseline

ACTIVE_CHAOS_SCENARIO = None

SCENARIOS = {
    "retriever_latency_spike": {
        "name": "INC-2026-0042: Retriever Top-K Context Blowout",
        "description": "Configuration update sets top_k=30 (up from 5). Causes p95 latency to spike 462% (2.1s -> 11.8s), token costs to surge 366%, and answer quality to degrade.",
        "severity": "HIGH",
        "config_mutation": {
            "top_k": 30,
            "reranker_enabled": False,
            "similarity_threshold": 0.40
        }
    },
    "hallucination_drift": {
        "name": "INC-2026-0088: Low-Similarity Retrieval Hallucination Drift",
        "description": "Similarity threshold reduced to 0.15 with high temperature (0.9), injecting noisy irrelevancies and dropping groundedness from 94% to 68%.",
        "severity": "HIGH",
        "config_mutation": {
            "similarity_threshold": 0.15,
            "temperature": 0.9,
            "top_k": 15
        }
    },
    "timeout_cascade": {
        "name": "INC-2026-0105: Tight Timeout Cascade with Zero Retries",
        "description": "Timeout reduced to 0.8s with retry_attempts=0, causing high rate of 504 Gateway Timeouts under moderate load.",
        "severity": "CRITICAL",
        "config_mutation": {
            "timeout_seconds": 0.8,
            "retry_attempts": 0
        }
    }
}

def inject_scenario(scenario_id: str) -> Dict[str, Any]:
    global ACTIVE_CHAOS_SCENARIO
    if scenario_id not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario_id}. Available: {list(SCENARIOS.keys())}")
    
    scenario = SCENARIOS[scenario_id]
    update_config_fields(**scenario["config_mutation"])
    ACTIVE_CHAOS_SCENARIO = scenario_id
    return {
        "status": "injected",
        "scenario_id": scenario_id,
        "scenario_name": scenario["name"],
        "severity": scenario["severity"],
        "applied_config": scenario["config_mutation"]
    }

def clear_chaos() -> Dict[str, Any]:
    global ACTIVE_CHAOS_SCENARIO
    ACTIVE_CHAOS_SCENARIO = None
    return {
        "status": "cleared",
        "active_config": get_config().model_dump()
    }

def get_active_chaos():
    return ACTIVE_CHAOS_SCENARIO
