# SentinelAI: Live System Demonstration & Incident Playbook

## Purpose
A guided demonstration walkthrough for evaluating SentinelAI's autonomous reliability engineering, root cause analysis, and automated Pull Request remediation capabilities on production Agentic AI and RAG applications.

---

## Executive Summary
> "SentinelAI provides automated reliability engineering for production Agentic AI systems: continuously monitoring latency, cost, and hallucination scores, autonomously diagnosing root causes, running sandboxed regression tests, and opening human-reviewed GitHub Pull Requests to safely remediate incidents."

---

## Step-by-Step Demo Flow

### 1. Steady State Observation
- Open Mission Control (`http://localhost:5173`).
- Observe the real-time telemetry:
  - p95 Latency: ~2.1s (healthy)
  - Cost / Request: ~$0.03 (nominal)
  - Groundedness: 94.5% (above 90% SLO)
  - Live query traffic streaming continuously.

### 2. Inject Fault (Chaos Studio)
- In the **Chaos Engineering Studio**, click **"INC-2026-0042: Top-K Context Blowout"**.
- Observe the immediate impact:
  - p95 Latency jumps to **11.8s** (+462%).
  - Cost per request escalates to **$0.14** (+366%).
  - Groundedness drops to **81.2%**.
  - System status switches to **"INCIDENT IN PROGRESS"**.

### 3. Trace the Autonomous Multi-Agent Loop
- View the **Autonomous Incident Remediation Trace**:
  - **Detection Agent**: Triages anomalies and sets severity to `HIGH`.
  - **Diagnosis Agent**: Pinpoints root cause (`top_k=30` without reranking) with 92% confidence.
  - **Remediation Agent**: Synthesizes surgical patch (`top_k=8` + `reranker_enabled=True`).
  - **Validation Agent**: Runs Pytest + RAG golden eval benchmark in isolated sandbox (all 5 passed).
  - **GitHub Agent**: Creates branch `fix/inc-2026-0042-retriever-latency` and opens Pull Request.

### 4. Human-in-the-Loop Review & Approval
- Click **"Review PR"** to open the PR modal:
  - Inspect the **Sandbox Validation Scorecard** (Before vs After comparison).
  - Inspect the **Surgical Code Diff**.
  - Review the **Safety Covenant**: Verify that autonomous agents cannot auto-merge without human sign-off.
- Enter your name as the Reviewer and click **"Approve & Merge to Main"**.

### 5. Verified Recovery
- Observe the PR status update to **MERGED & DEPLOYED**.
- Observe live charts: p95 latency drops back down to ~2.2s, cost normalizes to $0.03, and the system returns to **"PRODUCTION HEALTHY"**.
- View the **AI Safety Covenant Audit Trail** verifying that human authorization was logged.
