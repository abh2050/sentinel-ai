# 🛡️ SentinelAI: Autonomous AI Reliability & Incident Response Platform
### *Detect. Diagnose. Propose. Validate. Human Approves.*

[![Tests](https://img.shields.io/badge/Pytest-Passing-emerald)](tests/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-blue)](api/server.py)
[![React](https://img.shields.io/badge/React-18-cyan)](dashboard/)
[![Safety](https://img.shields.io/badge/AI_Safety-Human--in--the--Loop-amber)](sentinel_core/safety_policy.py)

**SentinelAI** is an autonomous reliability platform designed to detect, diagnose, remediate, and validate production AI/RAG incidents, culminating in **automated GitHub Pull Request creation with mandatory human review**.

---

## 🌟 Why This Project Stands Out for FDE & Applied AI Roles

Most AI portfolios showcase simple prompt wrappers or basic chatbots. **SentinelAI demonstrates end-to-end operational engineering for enterprise AI**:

1. **Continuous Telemetry & Observability**: OpenTelemetry-style tracking of p50/p95/p99 latency, per-request token costs, retrieval volume, and RAG Triad scores (Groundedness, Context Relevance, Answer Quality).
2. **Multi-Agent Incident Response**: Specialized autonomous agents for Detection, Root Cause Analysis (RCA), Remediation Synthesis, and Sandbox Validation.
3. **Automated Sandbox Benchmarking**: Runs unit tests (`pytest`) and RAG quality evaluations in an isolated container sandbox before touching git branches.
4. **Automated Pull Request Remediation**: Generates clean git branches, commits, and rich Markdown PR descriptions with validation scorecards.
5. **Strict AI Safety Covenant**: Enforces strict enterprise governance—AI agents are permitted to investigate and propose fixes, but **strictly prohibited from auto-merging or deploying without human sign-off**.

---

## 🏗️ Architecture

```text
                         AI APPLICATION (RAG & Agent Microservice)
                                            │
                         Telemetry Spans & Evaluation Metrics
                                            ▼
                           OBSERVABILITY & ANOMALY ENGINE
                         (Z-Scores, Cost, Latency Drift)
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
                      └────────────────────┬─────────────────────┘
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

## 🔬 Walkthrough of Incident INC-2026-0042

### 1. The Incident
A rogue commit or misconfiguration bumps retriever `top_k` from `5` to `30`:
- **p95 Latency**: 2.1s -> **11.8s** (+462%)
- **Cost / Request**: $0.03 -> **$0.14** (+366%)
- **Answer Groundedness**: 94.5% -> **81.2%** (Context dilution)

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

## 📄 License
Apache 2.0. Built for production AI reliability engineering portfolios.
