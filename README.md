# 🛡️ SentinelAI: Autonomous AI Reliability & Incident Response Platform
### *Continuous Telemetry • Autonomous Root-Cause Analysis • Sandboxed Remediation • Human-in-the-Loop PR Governance*

[![Tests](https://img.shields.io/badge/Pytest-Passing-emerald)](tests/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-blue)](api/server.py)
[![React](https://img.shields.io/badge/React-18-cyan)](dashboard/)
[![Safety](https://img.shields.io/badge/AI_Safety-Human--in--the--Loop-amber)](sentinel_core/safety_policy.py)

**SentinelAI** is an enterprise-grade autonomous reliability and incident remediation platform for **Agentic AI applications and production RAG pipelines**. It continuously monitors latency, token cost, retrieval volume, hallucination rates, and tool/agent execution failures.

When an incident is detected, SentinelAI autonomously isolates the root cause, synthesizes a surgical code or configuration remediation, benchmarks the fix in an isolated sandbox, and **opens a structured GitHub Pull Request with mandatory human review**.

---

## 🌟 Key Capabilities for Agentic AI Systems

Operating autonomous agentic workflows and RAG systems in production presents unique failure modes: prompt/context explosion, cascading agent retries, hallucination drift, and unpredictable token costs. SentinelAI solves this through an autonomous closed-loop reliability architecture:

1. **Continuous Telemetry & Agent Observability**: OpenTelemetry-compatible tracking of p50/p95/p99 latency, per-request token costs, context chunk volume, agent tool execution spans, and RAG Triad scores (Groundedness, Context Relevance, Answer Quality).
2. **Autonomous Multi-Agent Investigation**: Specialized agents for Detection & Triage, Root Cause Analysis (RCA), Remediation Synthesis, and Sandbox Validation.
3. **Automated Sandbox Benchmarking**: Executes unit tests (`pytest`) and golden evaluation benchmarks in an isolated container sandbox before any proposed change is committed.
4. **Automated Pull Request Remediation**: Generates clean git branches, commits, and rich Markdown PR descriptions with validation scorecards and before/after comparisons.
5. **Hardcoded AI Safety Covenant**: Enforces strict enterprise governance—AI agents are permitted to investigate and propose fixes, but are **strictly prohibited from auto-merging or deploying without human sign-off**.

---

## 🏗️ Architecture

```text
                     AGENTIC AI APPLICATION / RAG SERVICE
                                       │
                      Telemetry Spans, Spans & Triad Evals
                                       ▼
                        ┌─────────────────────────────┐
                        │    OBSERVABILITY ENGINE     │
                        │  Latency, Cost, Triad Evals │
                        └──────────────┬──────────────┘
                                       │
                               Incident Detected
                                       ▼
                 ┌──────────────────────────────────────────┐
                 │      SENTINEL MULTI-AGENT PIPELINE       │
                 │                                          │
                 │  1. Detection Agent (Severity & Triage)  │
                 │  2. Diagnosis Agent (RCA & Evidence)     │
                 │  3. Remediation Agent (Code & Config)    │
                 │  4. Validation Agent (Pytest & Sandbox)  │
                 │  5. GitHub Agent (Branch & PR Payload)   │
                 └─────────────────────┬────────────────────┘
                                       │
                                       ▼
                            SAFETY POLICY ENFORCER
                         (AI May NOT Auto-Merge/Deploy)
                                       │
                                       ▼
                        HUMAN-IN-THE-LOOP MISSION CONTROL
                      (Interactive Diff, PR Review & Merge)
```

---

## 🚀 Quickstart (1-Command Launch)

### Prerequisites
- Python 3.10+
- Node.js 18+ and npm

### 1. Launch Platform
```bash
bash scripts/start.sh
```

- **Mission Control Dashboard**: `http://localhost:5173`
- **FastAPI REST API / Docs**: `http://localhost:8000/docs`

### 2. Run Test Suite
```bash
bash scripts/test.sh
```

---

## 🔬 Incident Lifecycle: INC-2026-0042 (Top-K Context Blowout)

### 1. Detection
A configuration drift or rogue commit increases retrieval `top_k` from `5` to `30`:
- **p95 Latency**: 2.1s -> **11.8s** (+462%)
- **Cost / Request**: $0.03 -> **$0.14** (+366%)
- **Answer Groundedness**: 94.5% -> **81.2%** (Context dilution & attention loss)

### 2. Autonomous Diagnosis & Remediation
- **Diagnosis Agent**: Identifies quadratic token bloat in prompt context as the root cause (92% confidence).
- **Remediation Agent**: Proposes two-stage retrieval: candidate recall `top_k = 8` + Cross-Encoder Flash-Reranker `top_n = 5`.
- **Validation Agent**: Runs unit tests and synthetic benchmark in sandbox:
  - Latency: **11.8s -> 2.4s** (-79.6%)
  - Cost: **$0.14 -> $0.04** (-71.4%)
  - Groundedness: **81.2% -> 95.8%** (+14.6%)
  - Pytest Suite: **5/5 Passed**

### 3. Automated Pull Request & Human Review
The agent opens Pull Request `fix/inc-2026-0042-retriever-latency` containing the validation scorecard.
The Lead SRE reviews the diff in the mission control console, clicks **"Approve & Merge"**, and the fix is safely deployed.

---

## 🛡️ The AI Safety Covenant

```text
AI AGENTS ARE PERMITTED TO:
✓ Detect and correlate metric anomalies
✓ Investigate root causes and trace spans
✓ Synthesize surgical code and config patches
✓ Create git branches and run sandbox test suites
✓ Open Pull Requests with validation scorecards

AI AGENTS ARE PROHIBITED FROM:
✗ Auto-merging Pull Requests to production
✗ Pushing directly to protected branches (main/prod)
✗ Overriding failed tests or regression checks
✗ Disabling monitoring or alerting rules
```

---

## 📁 Repository Structure

```
sentinel-ai/
├── rag_service/              # Production AI Service & Chaos Simulator
│   ├── config.py             # Active runtime parameters (top_k, reranker)
│   ├── knowledge_base.py     # Enterprise knowledge corpus & vector embeddings
│   ├── rag_engine.py         # Dense retrieval, reranker & generation pipeline
│   └── chaos_injector.py     # Fault injection scenarios (INC-0042, INC-0088)
├── observability/            # Telemetry & Anomaly Detection
│   ├── metrics_collector.py  # Rolling timeseries (p50/p95, cost, RAG triad)
│   └── anomaly_detector.py   # Multi-metric dynamic z-score anomaly detector
├── sentinel_core/            # Autonomous Multi-Agent Reliability Engine
│   ├── models.py             # Pydantic schemas (Incidents, RCA, PRs)
│   ├── safety_policy.py      # Hardcoded AI Safety Covenant
│   ├── agents/               # Detection, Diagnosis, Remediation, Validation, GitHub
│   └── orchestrator.py       # State-machine coordinating lifecycle
├── api/                      # FastAPI Mission Control Backend
│   ├── server.py             # REST API & WebSocket/SSE endpoints
│   └── traffic_generator.py  # Continuous background query generator
├── dashboard/                # Modern SaaS Mission Control Web UI
│   ├── src/App.jsx           # Main mission control layout
│   └── src/components/       # MetricCards, LiveCharts, ChaosControls, PRModal
├── tests/                    # Pytest unit & end-to-end incident test suite
├── scripts/                  # start.sh, test.sh
└── README.md                 # System documentation
```

---

## 📄 License
Apache 2.0. Distributed for production AI reliability engineering.
