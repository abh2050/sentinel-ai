# Running SentinelAI in Production

This guide covers taking SentinelAI from the self-contained demo to a deployment that watches your real AI service and opens real pull requests.

Read [What Is Real and What Is Simulated](#what-is-real-and-what-is-simulated) first. Some components are production-shaped and some are demonstration scaffolding, and knowing which is which determines how much work adoption actually is.

---

## What Is Real and What Is Simulated

| Component | State | What adoption requires |
| :--- | :--- | :--- |
| **Telemetry ingestion** | Production-ready | Point connectors at your backends. No code changes. |
| **Canonical schema & unit reconciliation** | Production-ready | Extend the field mapping if you track extra metrics. |
| **Data quality gates** | Production-ready | Tune thresholds to your traffic profile. |
| **Anomaly detection** | Works, needs tuning | Baselines are static constants; replace with learned baselines. |
| **Root cause analysis** | Production-ready | Set an Anthropic API key. Falls back to a rule set without one. |
| **Pull request creation** | Production-ready | Set a GitHub token and repository. |
| **Safety policy enforcement** | Production-ready | Review the permitted/forbidden action lists. |
| **Sandbox validation** | Production-ready | Runs the real test suite in an isolated copy. |
| **Remediation synthesis** | **Demonstration only** | Patches one known parameter set. Requires real implementation. |
| **RAG service (`rag_service/`)** | **Demonstration only** | A simulator. Delete it and point ingestion at your real service. |

The honest summary: **the data pipeline, safety governance, PR delivery, sandbox validation, and root-cause analysis are real. Remediation synthesis is the remaining hardcoded piece**, and it sits behind an interface designed for a real implementation — see [Replacing the Remediation Agent](#replacing-the-remediation-agent).

---

## Quick Start

```bash
cp .env.example .env
# Edit .env: set SENTINEL_DEPLOYMENT_MODE=production and your GitHub credentials
docker compose up -d
curl http://localhost:8000/api/health
```

The health endpoint reports the deployment posture and any configuration problems. **Check `config_warnings` is empty before considering the deployment done.**

---

## Deployment Modes

`SENTINEL_DEPLOYMENT_MODE` controls whether demo scaffolding is active.

| | `demo` | `production` |
| :--- | :--- | :--- |
| Synthetic traffic generator | on | **off** |
| Chaos injection endpoints | on | **off** (403) |
| CORS default | `*` | **deny-all** |
| Ingestion poller | off (manual) | **every 30s** |
| GitHub integration | simulated | live (when configured) |

Production defaults are chosen so a partially-configured deploy **fails closed**. A synthetic traffic generator left running in production would pollute real telemetry with fake requests; a chaos endpoint left exposed would let anyone who can reach the service mutate live retrieval configuration.

---

## Connecting Your Telemetry

Edit `config/ingestion_sources.json`. Replace each `fixture_path` with an `endpoint`:

```jsonc
{
  "sources": [
    {
      "kind": "prometheus",
      "name": "prometheus-prod",
      "endpoint": "http://prometheus.internal:9090/api/v1/query_range",
      "query_params": {
        "query": "rag_request_latency_p95_seconds",
        "step": "10s"
      },
      "headers": { "Authorization": "Bearer ${PROMETHEUS_TOKEN}" },
      "service_name": "your-rag-service",
      "environment": "production"
    }
  ]
}
```

Four connector kinds ship: `otlp`, `prometheus`, `datadog`, `jsonl`. Delete the sources you don't use — an unreachable source is reported as unhealthy on every cycle rather than silently ignored.

### Mapping your metric names

Each connector declares which upstream metric feeds which canonical field. If your metrics are named differently, edit the connector's `columns` (metrics backends) or `SourceMapping` rules (event sources). For Prometheus, that is `ingestion/connectors/prometheus.py`:

```python
SeriesColumn("your_latency_metric_name", "latency_seconds", "to_float", required=True),
SeriesColumn("your_cost_metric_name",    "cost_usd",        "to_float"),
```

The third argument is the unit converter. Getting this wrong is the most likely integration mistake — a latency metric in milliseconds mapped as `to_float` instead of `ms_to_s` will read as 2100 seconds and be quarantined by the range gate. That quarantine is the system telling you the mapping is wrong; check `/api/ingestion/report` after your first cycle.

### Adding a backend that isn't supported

Subclass `TelemetryConnector` (event sources) or `MetricSeriesConnector` (metrics backends), declare a `SourceMapping`, and register it:

```python
from ingestion.connectors.registry import register_connector
register_connector("honeycomb", HoneycombConnector)
```

### Verifying the connection

```bash
curl -X POST http://localhost:8000/api/ingestion/run | jq '.report'
```

Check `sources_healthy` equals your source count, and that `quality.rejections_by_reason` is empty or explainable. A high `implausible_latency` count almost always means a unit converter mismatch.

---

## Connecting GitHub

Create a **fine-grained personal access token** (or GitHub App installation token) scoped to the repository holding your AI service configuration:

- **Contents**: read and write — create the branch and commit the patch
- **Pull requests**: read and write — open the PR

**Do not grant merge or administration permissions.** The safety covenant forbids autonomous merges, and `GitHubClient` exposes no merge method at all. Withholding the permission means the policy holds even if the code is later changed.

```bash
SENTINEL_GITHUB_ENABLED=true
SENTINEL_GITHUB_TOKEN=github_pat_...
SENTINEL_GITHUB_REPOSITORY=your-org/your-ai-platform
SENTINEL_GITHUB_BASE_BRANCH=main
# GitHub Enterprise:
# SENTINEL_GITHUB_API_URL=https://github.your-company.com/api/v3
```

Protect the base branch with a required review. SentinelAI is designed to be blocked by that rule, not to work around it.

If GitHub is enabled but incompletely configured, PR creation **degrades to simulated** rather than crashing the incident pipeline — losing a completed investigation because a token was missing is worse than delivering a clearly-labelled simulated PR. Simulated PRs carry `"simulated": true` in the API response.

---

## Securing the Deployment

### Authentication

```bash
SENTINEL_API_KEY=$(openssl rand -hex 32)
```

Every `/api` route except `/api/health` then requires a matching `X-API-Key` header. This is a second line of defence, **not a substitute for putting the service behind an authenticating proxy** — it is a single shared secret with no rotation, expiry, or per-user identity.

### CORS

```bash
SENTINEL_CORS_ORIGINS=https://sentinel.your-company.com
```

Production defaults to deny-all. Credentialed requests are only permitted once origins are explicitly listed, because browsers reject `Allow-Credentials` paired with a wildcard origin.

### Checklist

- [ ] `SENTINEL_DEPLOYMENT_MODE=production`
- [ ] `/api/health` returns an empty `config_warnings`
- [ ] `SENTINEL_API_KEY` set, or an authenticating proxy in front
- [ ] `SENTINEL_CORS_ORIGINS` set to your dashboard origin
- [ ] GitHub token has **no** merge permission
- [ ] Base branch protected with required review
- [ ] Chaos endpoints confirmed returning 403
- [ ] `.env` is not committed

---

## Operating It

### Health and observability

`GET /api/health` is unauthenticated and reports deployment mode, GitHub integration status, and configuration warnings. Use it as your liveness and readiness probe.

Every ingestion cycle logs its result:

```
INFO sentinel.api: ingestion cycle: 189 records loaded from 4/4 healthy sources
```

Alert on `sources_healthy` dropping below `sources_configured` — that means a telemetry backend is unreachable and SentinelAI is running partially blind.

### State and persistence

**Incidents and metrics are in-memory.** A restart loses incident history and the rolling metric window; the canonical-record landing zone (`data/landing/`) survives because it is a volume. For durable incident history, implement a persistent store behind `SentinelOrchestrator.active_incidents`.

### Scaling

Run **one instance**. The orchestrator, metrics collector, and dedup gate all hold in-process state, so a second replica would maintain an independent view of system health and could open duplicate pull requests for the same incident. Horizontal scaling requires externalizing that state first.

---

## Connecting the Model

The Diagnosis Agent uses Claude to determine root cause. Give it a key:

```bash
ANTHROPIC_API_KEY=sk-ant-...
SENTINEL_LLM_MODEL=claude-opus-5
SENTINEL_LLM_EFFORT=high        # low | medium | high | xhigh | max
```

Without a key it falls back to a deterministic rule set, so the platform runs either way — but the fallback only understands the one incident type it ships with. `/api/health` reports which path is active, and every `DiagnosisReport` carries `llm_backed` and `analysis_source` so a reviewer can tell a model verdict from a rule-based one.

### What the agent can and cannot do

It holds four tools, all read-only: current metrics against baseline, the live retrieval config, recent configuration changes, and a runbook search. It decides which to call and when it has enough evidence, then submits a structured verdict through a `submit_diagnosis` tool.

**The tools cannot mutate anything.** That is the containment boundary: the worst outcome of a model mistake is a wrong explanation attached to an incident, never a wrong change to the service. The patch is produced by deterministic code downstream, and it still has to pass sandbox validation and human review before it reaches production.

### Cost

One diagnosis is a handful of tool calls plus a verdict — a few cents at Opus pricing, once per incident. If that matters at your incident volume, drop `SENTINEL_LLM_EFFORT` to `medium`, or set `SENTINEL_LLM_MODEL=claude-sonnet-5`. Measure before assuming the cheaper setting is worse; root-cause analysis on a well-scoped incident is not a hard reasoning task.

### Extending it

To diagnose incident types beyond retrieval misconfiguration, give the agent more tools rather than more prompt. Useful additions: deployment history, feature-flag state, upstream dependency health, and recent traces sampled around the incident window. The system prompt in `sentinel_core/integrations/llm_client.py` deliberately asks for mechanism rather than correlation — keep that framing when you extend it.

---

## Replacing the Remediation Agent

Remediation is the remaining hardcoded stage: it patches one known parameter set. It sits behind a clean interface, so it can be replaced independently.

It must populate `RemediationProposal.file_changes` — a mapping of repository path to **complete new file content**, which is what actually gets committed. The `diff` field is display-only.

The shipped implementation reads the live config file and rewrites the retrieval parameters by regex, in **all four places they appear** — the two Pydantic field declarations and the two literals inside `reset_to_healthy_baseline()`. That last part matters: patching only the declarations leaves the reset function returning the old values, and since `clear_chaos()` calls it, the merged fix would be silently reverted the first time anything reset the service. If you write your own, check for the same class of partial patch.

It returns an empty change set when the file no longer matches its expectations or when the fix is already applied. Empty makes the GitHub client refuse to open the pull request, which is correct — a PR that changes nothing while claiming to fix an incident is worse than no PR.

**Using a model here is a bigger step than diagnosis.** Model-generated code goes into a commit, so the containment argument that makes the diagnosis agent safe does not carry over. If you do it, keep sandbox validation mandatory and treat the test suite as the real gate.

---

## Tuning Detection

`observability/anomaly_detector.py` uses static baselines and a 1.5x firing threshold:

```python
self.baseline = {"p95_latency": 2.1, "avg_cost_usd": 0.030, ...}
```

For production, replace these with baselines learned from your own traffic — a rolling percentile over a trailing window, or a seasonal model if your load has daily shape. Two failure modes to avoid:

- **Baseline above the firing threshold** — the detector fires constantly and gets ignored. Verify your healthy p95 sits comfortably below `baseline * 1.5`.
- **Baseline learned during an incident** — the degraded state becomes the new normal and the regression never alerts. Exclude periods with an open incident from baseline computation.

Quality gate thresholds in `ingestion/validation.py` may also need widening: `RangeGate` rejects latencies above 600s as implausible, which is correct for interactive RAG and wrong for long-running agentic workflows.

---

## Deploying Without Docker

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd dashboard && npm ci && npm run build && cd ..

export SENTINEL_DEPLOYMENT_MODE=production
export SENTINEL_CORS_ORIGINS=https://sentinel.your-company.com
export SENTINEL_API_KEY=...

.venv/bin/uvicorn api.server:app --host 0.0.0.0 --port 8000
```

The API serves the built dashboard from `dashboard/dist` when present, so a single process covers both. Do not use `scripts/start.sh` in production — it runs the Vite dev server and enables reload.
