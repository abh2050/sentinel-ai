import React, { useState, useEffect } from 'react'
import {
  Database, Play, RefreshCw, CheckCircle2, AlertTriangle,
  Activity, ArrowRight, ShieldCheck
} from 'lucide-react'

const KIND_STYLES = {
  otlp: { label: 'OpenTelemetry', color: 'bg-violet-500/10 text-violet-300 border-violet-500/30' },
  prometheus: { label: 'Prometheus', color: 'bg-orange-500/10 text-orange-300 border-orange-500/30' },
  datadog: { label: 'Datadog', color: 'bg-purple-500/10 text-purple-300 border-purple-500/30' },
  jsonl: { label: 'App Logs', color: 'bg-sky-500/10 text-sky-300 border-sky-500/30' },
}

export default function IngestionPanel() {
  const [sources, setSources] = useState([])
  const [report, setReport] = useState(null)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    const load = async () => {
      try {
        const [srcRes, repRes] = await Promise.all([
          fetch('/api/ingestion/sources').then(r => r.json()),
          fetch('/api/ingestion/report').then(r => r.json()),
        ])
        setSources(srcRes.sources || [])
        if (repRes.has_run) setReport(repRes.report)
      } catch (err) {
        console.error('Ingestion fetch error:', err)
      }
    }
    load()
  }, [])

  const handleRun = async () => {
    setRunning(true)
    try {
      const res = await fetch('/api/ingestion/run', { method: 'POST' }).then(r => r.json())
      if (res.report) setReport(res.report)
    } catch (err) {
      console.error('Ingestion run error:', err)
    } finally {
      setRunning(false)
    }
  }

  const handleReset = async () => {
    setRunning(true)
    try {
      await fetch('/api/ingestion/reset', { method: 'POST' })
      setReport(null)
    } catch (err) {
      console.error('Ingestion reset error:', err)
    } finally {
      setRunning(false)
    }
  }

  const quality = report?.quality
  const rejectionReasons = Object.entries(quality?.rejections_by_reason || {})

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Database className="w-4 h-4 text-cyan-400" />
          <h3 className="text-sm font-semibold text-zinc-200">
            Telemetry Ingestion Pipeline
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleReset}
            disabled={running}
            className="flex items-center gap-1.5 px-3 py-1 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-mono transition-colors border border-zinc-700 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${running ? 'animate-spin' : ''}`} />
            Rewind
          </button>
          <button
            onClick={handleRun}
            disabled={running}
            className="flex items-center gap-1.5 px-3 py-1 rounded-md bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-mono transition-colors border border-cyan-500 disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5" />
            {running ? 'Ingesting…' : 'Run Ingestion Cycle'}
          </button>
        </div>
      </div>

      {/* Pipeline stage flow */}
      <div className="flex items-center gap-2 mb-4 text-[10px] font-mono text-zinc-500 flex-wrap">
        {['Extract', 'Normalize', 'Enrich', 'Validate', 'Load'].map((stage, i, arr) => (
          <React.Fragment key={stage}>
            <span className="px-2 py-0.5 rounded bg-zinc-900 border border-border text-zinc-400">
              {stage}
            </span>
            {i < arr.length - 1 && <ArrowRight className="w-3 h-3 text-zinc-700" />}
          </React.Fragment>
        ))}
        <span className="ml-1 text-zinc-600">→ Anomaly Detector → Sentinel Agents</span>
      </div>

      {/* Connected sources */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        {sources.map((source) => {
          const style = KIND_STYLES[source.kind] || {
            label: source.kind, color: 'bg-zinc-500/10 text-zinc-300 border-zinc-500/30'
          }
          const stats = report?.sources?.find(s => s.source_name === source.name)

          return (
            <div
              key={source.name}
              className="p-3 rounded-lg border border-border bg-zinc-900/60 flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${style.color}`}>
                    {style.label}
                  </span>
                  {stats && (
                    stats.healthy
                      ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                      : <AlertTriangle className="w-3.5 h-3.5 text-red-500" />
                  )}
                </div>
                <p className="text-xs font-semibold text-zinc-200 truncate" title={source.name}>
                  {source.name}
                </p>
                <p className="text-[10px] text-zinc-500 font-mono mt-0.5">
                  {source.mode} · {source.environment}
                </p>
              </div>

              <div className="mt-2 pt-2 border-t border-border/40 text-[10px] font-mono">
                {stats ? (
                  <div className="flex items-center justify-between">
                    <span className="text-emerald-400">{stats.records_accepted} ok</span>
                    {stats.records_rejected > 0 && (
                      <span className="text-amber-400">{stats.records_rejected} rej</span>
                    )}
                  </div>
                ) : (
                  <span className="text-zinc-600">awaiting run</span>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Run report */}
      {report ? (
        <div className="rounded-lg border border-border bg-zinc-900/40 p-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <Stat
              icon={Activity}
              label="Records Read"
              value={report.total_read}
              tone="text-zinc-100"
            />
            <Stat
              icon={ArrowRight}
              label="Loaded to Telemetry"
              value={report.records_loaded}
              tone="text-cyan-400"
            />
            <Stat
              icon={ShieldCheck}
              label="Acceptance Rate"
              value={`${quality?.acceptance_rate_pct ?? 0}%`}
              tone="text-emerald-400"
            />
            <Stat
              icon={AlertTriangle}
              label="Quarantined"
              value={quality?.rejected ?? 0}
              tone={quality?.rejected ? 'text-amber-400' : 'text-zinc-400'}
            />
          </div>

          {rejectionReasons.length > 0 && (
            <div className="pt-2 border-t border-border/40">
              <p className="text-[10px] font-mono text-zinc-500 mb-1.5">
                DEAD-LETTER QUARANTINE — rejected before reaching the detector
              </p>
              <div className="flex flex-wrap gap-1.5">
                {rejectionReasons.map(([reason, count]) => (
                  <span
                    key={reason}
                    className="px-2 py-0.5 rounded text-[10px] font-mono bg-amber-500/10 text-amber-300 border border-amber-500/30"
                  >
                    {reason} × {count}
                  </span>
                ))}
              </div>
            </div>
          )}

          <p className="text-[10px] font-mono text-zinc-600 mt-2.5">
            {report.sources_healthy}/{report.sources_configured} sources healthy ·
            completed in {report.duration_seconds}s ·
            normalized to canonical schema (seconds / USD / 0-100)
          </p>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-border bg-zinc-900/20 p-4 text-center">
          <p className="text-xs text-zinc-500">
            Run a cycle to pull telemetry from all connected sources into the reliability platform.
          </p>
        </div>
      )}
    </div>
  )
}

function Stat({ icon: Icon, label, value, tone }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-0.5">
        <Icon className="w-3 h-3 text-zinc-600" />
        <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-wide">{label}</span>
      </div>
      <p className={`text-lg font-semibold font-mono ${tone}`}>{value}</p>
    </div>
  )
}
