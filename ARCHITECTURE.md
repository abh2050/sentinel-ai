# SentinelAI: System Architecture & Technical Specification

## 1. High-Level Vision
SentinelAI is an enterprise-grade autonomous reliability platform designed to operate production AI/RAG services. When production incidents occur (latency spikes, cost surges, hallucination drift), SentinelAI autonomously investigates telemetry, isolates the root cause, synthesizes a surgical code/configuration remediation, benchmarks the fix in an isolated sandbox, and **opens a structured GitHub Pull Request with mandatory human review**.

```text
                         PRODUCTION AI APPLICATION
                                     │
                        Telemetry, Spans & Triad Evals
                                     ▼
                      ┌─────────────────────────────┐
                      │    OBSERVABILITY ENGINE     │
                      │  p95 Latency, Cost, Chunks  │
                      └──────────────┬──────────────┘
                                     │
                              Incident Detected
                                     ▼
                      ┌─────────────────────────────┐
                      │      DETECTION AGENT        │
                      │   Classify & Triage Severity │
                      └──────────────┬──────────────┘
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │      DIAGNOSIS AGENT        │
                      │    RCA & Evidence Mining    │
                      └──────────────┬──────────────┘
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │     REMEDIATION AGENT       │
                      │  Synthesize Code/Config Fix │
                      └──────────────┬──────────────┘
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │      VALIDATION AGENT       │
                      │   Pytest + RAG Benchmarks   │
                      └──────────────┬──────────────┘
                                     │
                               Validation Pass
                                     ▼
                      ┌─────────────────────────────┐
                      │     GITHUB PR AGENT         │
                      │   Branch, Commit & Open PR  │
                      └──────────────┬──────────────┘
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │    MANDATORY HUMAN REVIEW   │
                      │  Approve & Deploy to Main   │
                      └─────────────────────────────┘
```

---

## 2. Component Breakdown

### A. Observability & Anomaly Telemetry Engine (`observability/`)
- **Metrics Tracked**:
  - `p50`, `p95`, `p99` Request Latency
  - Cost per Request ($ USD) based on input/output token weights
  - Retrieved Context Chunk Volume
  - RAG Triad Metrics: Answer Groundedness, Context Relevance, Answer Quality
  - API Error Rate
- **Anomaly Detection**:
  - Compares sliding window averages against statistical baselines (`p95_latency > 1.5x baseline`, `cost > 1.5x baseline`).
  - Correlates multi-metric anomalies and packages structured incident payloads (`INC-2026-0042`).

### B. Sentinel Multi-Agent Pipeline (`sentinel_core/`)
1. **Detection Agent (`detection_agent.py`)**:
   - Ingests anomaly snapshots, computes blast radius, and assigns severity (`CRITICAL`, `HIGH`, `MEDIUM`).
2. **Diagnosis Agent (`diagnosis_agent.py`)**:
   - Analyzes telemetry streams, recent git commits, and config mutations.
   - Calculates diagnostic confidence (e.g. 92%) and isolates causal mechanisms (e.g. `top_k=30` causing quadratic prompt token bloat).
3. **Remediation Agent (`remediation_agent.py`)**:
   - Synthesizes surgical patches to `rag_service/config.py` (e.g. reducing `top_k=8`, activating `reranker_enabled=True`, and bounding context limits).
   - Generates git branch naming (`fix/inc-2026-0042-retriever-latency`) and commit metadata.
4. **Validation Agent (`validation_agent.py`)**:
   - Executes Pytest test suites in a sandboxed runner.
   - Benchmarks response quality across synthetic golden evaluation sets to verify latency recovery (11.8s -> 2.4s) and cost savings (-71%).
   - **Safety Boundary**: Halts PR creation if unit tests fail or regressions occur.
5. **GitHub Integration Agent (`github_agent.py`)**:
   - Opens structured Pull Requests formatted with incident tables, root-cause summaries, before/after scorecards, and human review notices.

### C. Safety Covenant & Governance Enforcer (`safety_policy.py`)
Hardcoded architectural rules:

| Action | AI Permission | Human Operator Permission |
| :--- | :---: | :---: |
| **Detect Incidents** | ✅ PERMITTED | ✅ PERMITTED |
| **Investigate Root Cause** | ✅ PERMITTED | ✅ PERMITTED |
| **Synthesize Fixes** | ✅ PERMITTED | ✅ PERMITTED |
| **Create Branches & Tests** | ✅ PERMITTED | ✅ PERMITTED |
| **Open Pull Requests** | ✅ PERMITTED | ✅ PERMITTED |
| **Auto-Merge Pull Request** | 🚫 **BLOCKED** | ✅ **PERMITTED** |
| **Direct Push to Main/Prod** | 🚫 **BLOCKED** | ✅ **PERMITTED** |
| **Override Failed Tests** | 🚫 **BLOCKED** | ✅ **PERMITTED** |
