import React from 'react'
import { Clock, DollarSign, Layers, CheckCircle2, TrendingUp, TrendingDown, AlertCircle } from 'lucide-react'

export default function MetricCards({ metrics, systemStatus, activeIncident }) {
  const p95 = metrics?.p95_latency || 2.1
  const cost = metrics?.avg_cost_usd || 0.03
  const chunks = metrics?.avg_chunks || 5.0
  const groundedness = metrics?.avg_groundedness || 94.5
  const isIncident = p95 > 4.0 || cost > 0.06

  const cards = [
    {
      title: "p95 Latency",
      value: `${p95}s`,
      baseline: "Target: < 2.5s",
      change: isIncident ? "+462% spike" : "Nominal",
      icon: Clock,
      status: p95 > 4.0 ? "danger" : "normal",
      deltaType: isIncident ? "up" : "flat",
      subtext: `p50: ${metrics?.p50_latency || 1.8}s | p99: ${metrics?.p99_latency || 2.4}s`
    },
    {
      title: "Cost per Request",
      value: `$${cost.toFixed(3)}`,
      baseline: "Target: < $0.035",
      change: isIncident ? "+366% surge" : "Nominal",
      icon: DollarSign,
      status: cost > 0.06 ? "danger" : "normal",
      deltaType: isIncident ? "up" : "flat",
      subtext: `Avg Tokens: ${metrics?.avg_tokens || 1250} tokens/req`
    },
    {
      title: "Context Retrieval Chunks",
      value: `${Math.round(chunks)} chunks`,
      baseline: "Baseline: 5 chunks",
      change: chunks > 10 ? "+540% bloat" : "Optimal",
      icon: Layers,
      status: chunks > 10 ? "warning" : "normal",
      deltaType: chunks > 10 ? "up" : "flat",
      subtext: `Active Top-K: ${systemStatus?.config?.top_k || 5}`
    },
    {
      title: "Answer Groundedness",
      value: `${groundedness}%`,
      baseline: "SLO: > 90%",
      change: groundedness < 88 ? "-13.3% drift" : "Verified",
      icon: CheckCircle2,
      status: groundedness < 88 ? "danger" : "normal",
      deltaType: groundedness < 88 ? "down" : "flat",
      subtext: `Triad Quality: ${metrics?.avg_quality || 94.0}%`
    }
  ]

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((c, idx) => {
        const Icon = c.icon
        const isBad = c.status === "danger"
        const isWarn = c.status === "warning"

        return (
          <div
            key={idx}
            className={`relative overflow-hidden rounded-xl border p-4 transition-all duration-200 ${
              isBad
                ? 'bg-red-950/20 border-red-500/40 shadow-lg shadow-red-900/10'
                : isWarn
                ? 'bg-amber-950/20 border-amber-500/40 shadow-lg shadow-amber-900/10'
                : 'bg-card border-border hover:border-zinc-700'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-zinc-400">{c.title}</span>
              <div className={`p-1.5 rounded-md ${
                isBad ? 'bg-red-500/10 text-red-400' : isWarn ? 'bg-amber-500/10 text-amber-400' : 'bg-zinc-800 text-zinc-300'
              }`}>
                <Icon className="w-4 h-4" />
              </div>
            </div>

            <div className="mt-3 flex items-baseline justify-between">
              <span className={`text-2xl font-bold font-mono tracking-tight ${
                isBad ? 'text-red-400' : isWarn ? 'text-amber-400' : 'text-zinc-100'
              }`}>
                {c.value}
              </span>

              <span className={`text-xs font-mono font-medium flex items-center gap-0.5 ${
                isBad ? 'text-red-400' : isWarn ? 'text-amber-400' : 'text-emerald-400'
              }`}>
                {isBad ? <TrendingUp className="w-3 h-3" /> : isWarn ? <AlertCircle className="w-3 h-3" /> : <CheckCircle2 className="w-3 h-3" />}
                {c.change}
              </span>
            </div>

            <div className="mt-2 pt-2 border-t border-border/50 flex items-center justify-between text-[11px] text-zinc-400 font-mono">
              <span>{c.baseline}</span>
              <span className="text-zinc-400">{c.subtext}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
