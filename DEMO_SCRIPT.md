# SentinelAI: Live Demo & Interview Script

## 🎯 Target Audience
Hiring managers, Principal AI Engineers, and VP of Engineering evaluating Forward Deployed Engineer (FDE) or Applied AI capabilities.

---

## 🎙️ 2-Minute Elevator Pitch
> "Most AI portfolios stop at 'here is my chatbot'. SentinelAI demonstrates how to operate enterprise AI systems in production: continuously monitoring latency, cost, and hallucination scores, autonomously diagnosing root causes, running sandboxed regression tests, and opening human-reviewed GitHub Pull Requests to safely remediate incidents."

---

## 🎬 Step-by-Step Demo Flow

### 1. Steady State Observation
- Open Mission Control (`http://localhost:5173`).
- Point out the real-time telemetry:
  - p95 Latency: ~2.1s (healthy)
  - Cost / Request: ~$0.03 (nominal)
  - Groundedness: 94.5% (above 90% SLO)
  - Live query traffic streaming continuously.

### 2. Inject Fault (Chaos Studio)
- In the **Chaos Engineering Studio**, click **"INC-2026-0042: Top-K Context Blowout"**.
- Point out what happens instantly:
  - p95 Latency jumps to **11.8s** (+462%).
  - Cost per request escalates to **$0.14** (+366%).
  - Groundedness drops to **81.2%**.
  - System status switches to **"INCIDENT IN PROGRESS"**.

### 3. Trace the Autonomous Multi-Agent Loop
- Scroll to the **Autonomous Incident Remediation Trace**:
  - **Detection Agent**: Triage anomalies and sets severity to `HIGH`.
  - **Diagnosis Agent**: Pinpoints root cause (`top_k=30` without reranking) with 92% confidence.
  - **Remediation Agent**: Synthesizes surgical patch (`top_k=8` + `reranker_enabled=True`).
  - **Validation Agent**: Runs Pytest + RAG golden eval benchmark in isolated sandbox (all 5 passed).
  - **GitHub Agent**: Creates branch `fix/inc-2026-0042-retriever-latency` and opens Pull Request.

### 4. Human-in-the-Loop Review & Approval
- Click **"Review PR"** to open the PR modal:
  - Inspect the **Sandbox Validation Scorecard** (Before vs After comparison).
  - Inspect the **Surgical Code Diff**.
  - Highlight the **Safety Covenant**: Explain why autonomous agents MUST NOT auto-merge to production without human review.
- Enter your name as the Reviewer and click **"Approve & Merge to Main"**.

### 5. Verified Recovery
- Observe the PR status update to **MERGED & DEPLOYED**.
- Look at the live charts: p95 latency drops back down to ~2.2s, cost normalizes to $0.03, and the system returns to **"PRODUCTION HEALTHY"**.
- View the **AI Safety Covenant Audit Trail** verifying that human authorization was cryptographically logged.
