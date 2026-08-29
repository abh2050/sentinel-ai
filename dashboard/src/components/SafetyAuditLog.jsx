import React from 'react'
import { ShieldCheck, Lock, CheckCircle2, ShieldAlert } from 'lucide-react'

export default function SafetyAuditLog({ auditLogs }) {
  const logs = auditLogs || []

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
          <h3 className="text-sm font-semibold text-zinc-200">AI Safety Covenant & Governance Audit Trail</h3>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono text-zinc-400">
          <span className="flex items-center gap-1 text-emerald-400">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" /> Policy Enforced
          </span>
          <span className="flex items-center gap-1 text-amber-400">
            <Lock className="w-3 h-3" /> Auto-Merge Blocked
          </span>
        </div>
      </div>

      <div className="max-h-48 overflow-y-auto space-y-2 pr-1 text-xs font-mono">
        {logs.length === 0 ? (
          <div className="text-zinc-500 py-3 text-center text-xs">No audit events recorded yet.</div>
        ) : (
          logs.slice(0, 10).map((log, i) => (
            <div
              key={i}
              className={`p-2 rounded border flex items-start justify-between ${
                log.is_permitted_by_safety 
                  ? 'bg-zinc-900/60 border-border/60 text-zinc-300' 
                  : 'bg-red-950/20 border-red-500/30 text-red-300'
              }`}
            >
              <div className="flex items-start gap-2">
                <span className="text-[10px] text-zinc-500 shrink-0 mt-0.5">{log.time_str || "12:00:00"}</span>
                <div>
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-zinc-200">{log.action}</span>
                    <span className="text-[10px] text-zinc-400">by {log.agent_name}</span>
                  </div>
                  <p className="text-[11px] text-zinc-400 mt-0.5">{log.details}</p>
                </div>
              </div>

              <span className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${
                log.is_permitted_by_safety 
                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                  : 'bg-red-500/10 text-red-400 border border-red-500/20'
              }`}>
                {log.status}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
