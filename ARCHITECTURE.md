# SentinelAI: System Architecture & Technical Specification

## 1. High-Level Vision
SentinelAI is an enterprise-grade autonomous reliability platform designed to operate production AI/RAG services. When production incidents occur (latency spikes, cost surges, hallucination drift), SentinelAI autonomously investigates telemetry, isolates the root cause, synthesizes a surgical code/configuration remediation, benchmarks the fix in an isolated sandbox, and **opens a structured GitHub Pull Request with mandatory human review**.

```text
                         PRODUCTION AI APPLICATION
                                     │
              OTLP spans │ Prometheus │ Datadog │ App JSONL logs
                                     ▼
                      ┌─────────────────────────────┐
                      │ TELEMETRY INGESTION PIPELINE│
                      │ Normalize · Enrich · Validate│
                      └──────────────┬──────────────┘
                                     │ canonical records
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

> For the runtime interaction view — who calls whom, in what order, and where the safety gate refuses the AI — see the [Incident Lifecycle Sequence](README.md#incident-lifecycle-sequence) diagram in the README.

---

## 2. Component Breakdown

### A0. Telemetry Ingestion Pipeline (`ingestion/`)

The data-engineering layer that connects SentinelAI to whatever observability stack already exists.

**Stages** — `extract → normalize → enrich → validate → load`

1. **Extract** (`connectors/`): One connector per backend. Each declares only how to fetch a raw payload and a `SourceMapping`; record selection, field mapping, watermarking, and error isolation are handled by the base class. Every remote connector supports an offline `fixture_path` so the pipeline is runnable and testable without vendor credentials.

2. **Normalize** (`mapping.py`, `schema.py`): Declarative `FieldRule`s move vendor fields onto the `CanonicalTelemetryRecord` and apply a named unit converter. Canonical units are **seconds, USD, and 0–100** — reconciling nanosecond timestamps, micro-dollar billing, and 0–1 quality ratios across vendors. Adding a backend is a mapping declaration, not a new code path.

   Metrics backends (Prometheus, Datadog) return pre-aggregated *series* rather than per-request events. `connectors/series.py` pivots independent series onto a shared time grid to reconstruct wide records. Buckets missing a required column are dropped, never zero-filled.

3. **Enrich** (`transforms.py`): Derives fields a source omitted — `total_tokens` from its components, cost from token counts via a price book, canonical environment names from vendor spellings. Transforms are total and never raise; one failing transform cannot drop a record.

4. **Validate** (`validation.py`): Four gates — completeness, range, freshness, deduplication — each returning a named rejection reason. Rejected records land in a bounded dead-letter buffer for inspection. Gates are tuned to reject *corrupt* data while passing *bad news* (a genuine 11.8s request is signal and must reach the detector).

5. **Load** (`sinks.py`): Fans out to the live `MetricsCollector` and a durable JSONL landing zone. Records are merged across sources and sorted by event time before loading, since the collector maintains a rolling window and computes percentiles per arrival.

**Operational properties**
- **Fault isolation**: a fetch failure is captured per connector; one unreachable backend cannot stop ingestion from the others.
- **Watermarking**: each connector tracks the newest emitted event time so repeated polls don't replay history.
- **Deterministic ids**: `event_id` is derived from source, trace, and timestamp, making at-least-once delivery deduplicable.
- **Observability**: every run returns a structured report — per-source counts, acceptance rate, rejection reasons, dead-letter samples. A silent pipeline is indistinguishable from a healthy one.

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
