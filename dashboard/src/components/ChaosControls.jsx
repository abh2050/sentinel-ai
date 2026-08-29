import React from 'react'
import { Flame, RefreshCw, Zap, Bug, Clock, ShieldAlert } from 'lucide-react'

export default function ChaosControls({ onTriggerChaos, onReset, activeScenario, loading }) {
  const scenarios = [
    {
      id: "retriever_latency_spike",
      title: "INC-2026-0042: Top-K Context Blowout",
      description: "Sets top_k=30 (from 5). Causes p95 latency to spike 462% (11.8s) and token cost to quadruple.",
      icon: Clock,
      badge: "High Severity",
      badgeColor: "bg-red-500/10 text-red-400 border-red-500/30"
    },
    {
      id: "hallucination_drift",
      title: "INC-2026-0088: Groundedness Drift",
      description: "Lowers threshold to 0.15 + high temp (0.9), injecting noisy irrelevancies and dropping groundedness.",
      icon: Bug,
      badge: "Quality Drift",
      badgeColor: "bg-amber-500/10 text-amber-400 border-amber-500/30"
    },
    {
      id: "timeout_cascade",
      title: "INC-2026-0105: Tight Timeout Cascade",
      description: "Lowers timeout to 0.8s with 0 retries, inducing 504 Gateway errors under concurrent load.",
      icon: Zap,
      badge: "Availability",
      badgeColor: "bg-purple-500/10 text-purple-400 border-purple-500/30"
    }
  ]

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Flame className="w-4 h-4 text-orange-500" />
          <h3 className="text-sm font-semibold text-zinc-200">Chaos Engineering & Fault Injection Studio</h3>
        </div>
        <button
          onClick={onReset}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-mono transition-colors border border-zinc-700"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Reset to Baseline
        </button>
      </div>
      <p className="text-xs text-zinc-400 mb-4">
        Inject real-world production failures to test the autonomous multi-agent reliability and automated PR remediation loop.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {scenarios.map((s) => {
          const Icon = s.icon
          const isActive = activeScenario === s.id

          return (
            <button
              key={s.id}
              onClick={() => onTriggerChaos(s.id)}
              disabled={loading}
              className={`text-left p-3.5 rounded-lg border transition-all relative overflow-hidden flex flex-col justify-between ${
                isActive
                  ? 'bg-red-950/40 border-red-500 shadow-md shadow-red-900/20'
                  : 'bg-zinc-900/60 border-border hover:border-zinc-600 hover:bg-zinc-900'
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="p-1 rounded bg-zinc-800 text-zinc-300">
                    <Icon className="w-4 h-4" />
                  </div>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${s.badgeColor}`}>
                    {s.badge}
                  </span>
                </div>
                <h4 className="text-xs font-semibold text-zinc-100 mb-1">{s.title}</h4>
                <p className="text-[11px] text-zinc-400 leading-relaxed">{s.description}</p>
              </div>

              <div className="mt-3 pt-2 border-t border-border/40 flex items-center justify-between text-[10px] font-mono">
                <span className={isActive ? 'text-red-400 font-bold' : 'text-zinc-500'}>
                  {isActive ? '● ACTIVE FAULT' : 'Click to Inject'}
                </span>
                <span className="text-blue-400 hover:underline">Trigger RCA →</span>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
