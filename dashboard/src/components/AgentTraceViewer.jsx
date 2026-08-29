import React from 'react'
import { Bot, CheckCircle2, Clock, AlertTriangle, ArrowRight, ShieldCheck, GitPullRequest, Code2, FlaskConical, Stethoscope } from 'lucide-react'

export default function AgentTraceViewer({ incident, onOpenPRModal }) {
  if (!incident) {
    return (
      <div className="rounded-xl border border-border bg-card p-6 text-center text-zinc-500 font-mono text-xs">
        <Bot className="w-8 h-8 mx-auto mb-2 text-zinc-600" />
        No active incident. Inject a chaos scenario above to initiate the autonomous multi-agent response loop.
      </div>
    )
  }

  const steps = [
    {
      id: "detection",
      title: "1. Detection & Triage",
      agent: "Sentinel Detection Agent",
      icon: AlertTriangle,
      status: "DONE",
      details: incident.anomalies?.map(a => `${a.title}: ${a.current} (${a.change_pct})`).join(" • ") || "Anomalies detected and correlated."
    },
    {
      id: "diagnosis",
      title: "2. Root Cause Analysis (RCA)",
      agent: "Sentinel Diagnosis Agent",
      icon: Stethoscope,
      status: incident.diagnosis ? "DONE" : "RUNNING",
      details: incident.diagnosis ? `Confidence: ${Math.round(incident.diagnosis.confidence * 100)}% — ${incident.diagnosis.root_cause_summary}` : "Analyzing span traces and config diffs..."
    },
    {
      id: "remediation",
      title: "3. Remediation Synthesis",
      agent: "Sentinel Remediation Agent",
      icon: Code2,
      status: incident.remediation ? "DONE" : "PENDING",
      details: incident.remediation ? `Generated branch '${incident.remediation.branch_name}' with surgical config diff.` : "Synthesizing patch..."
    },
    {
      id: "validation",
      title: "4. Sandbox Validation",
      agent: "Sentinel Validation Agent",
      icon: FlaskConical,
      status: incident.validation ? "DONE" : "PENDING",
      details: incident.validation ? "5/5 Pytest passed • RAG Eval passed • Latency recovered (11.8s -> 2.4s)" : "Executing isolated tests..."
    },
    {
      id: "pr",
      title: "5. GitHub Pull Request",
      agent: "Sentinel GitHub Integration Agent",
      icon: GitPullRequest,
      status: incident.pull_request ? "DONE" : "PENDING",
      details: incident.pull_request ? `Opened PR #${incident.pull_request.pr_number} • Mandatory Human Review Required` : "Opening PR..."
    }
  ]

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Bot className="w-5 h-5 text-blue-500" />
          <h3 className="text-sm font-semibold text-zinc-100">
            Autonomous Incident Remediation Trace: <span className="font-mono text-blue-400">{incident.incident_id}</span>
          </h3>
        </div>
        <span className="px-2.5 py-1 rounded-full text-xs font-mono font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20">
          Status: {incident.status}
        </span>
      </div>

      {/* Multi-Agent Sequential Flow Pipeline */}
      <div className="space-y-3">
        {steps.map((step, idx) => {
          const Icon = step.icon
          const isDone = step.status === "DONE"
          const isRunning = step.status === "RUNNING"

          return (
            <div
              key={step.id}
              className={`p-3.5 rounded-lg border transition-all ${
                isDone 
                  ? 'bg-zinc-900/60 border-border/80' 
                  : isRunning 
                  ? 'bg-blue-950/20 border-blue-500/50 shadow-md' 
                  : 'bg-zinc-950/40 border-border/40 opacity-60'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <div className={`p-1.5 rounded-md mt-0.5 ${
                    isDone ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30' :
                    isRunning ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40 animate-pulse' :
                    'bg-zinc-800 text-zinc-500'
                  }`}>
                    <Icon className="w-4 h-4" />
                  </div>

                  <div>
                    <div className="flex items-center gap-2">
                      <h4 className="text-xs font-bold text-zinc-200">{step.title}</h4>
                      <span className="text-[10px] font-mono text-zinc-400">[{step.agent}]</span>
                    </div>
                    <p className="text-xs text-zinc-300 mt-1 leading-relaxed">{step.details}</p>
                  </div>
                </div>

                <div className="text-right font-mono text-[11px]">
                  {isDone ? (
                    <span className="text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" /> COMPLETE
                    </span>
                  ) : isRunning ? (
                    <span className="text-blue-400 flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5 animate-spin" /> RUNNING
                    </span>
                  ) : (
                    <span className="text-zinc-600">QUEUED</span>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {incident.pull_request && (
        <div className="mt-4 p-4 rounded-lg bg-blue-950/30 border border-blue-500/40 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-blue-600 text-white">
              <GitPullRequest className="w-5 h-5" />
            </div>
            <div>
              <h4 className="text-xs font-bold text-white">Pull Request #{incident.pull_request.pr_number} Awaiting Human Review</h4>
              <p className="text-xs text-blue-300">Under the AI Safety Covenant, this PR cannot auto-merge. Human approval required.</p>
            </div>
          </div>
          <button
            onClick={onOpenPRModal}
            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium font-mono transition-all shadow-md shadow-blue-600/30"
          >
            Open Review & Diff Modal →
          </button>
        </div>
      )}
    </div>
  )
}
