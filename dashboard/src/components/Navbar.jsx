import React from 'react'
import { Shield, Activity, GitPullRequest, Terminal, AlertTriangle, CheckCircle2 } from 'lucide-react'

export default function Navbar({ systemStatus, activeIncident, onOpenPRModal }) {
  const isIncident = systemStatus?.status === 'INCIDENT_ACTIVE' || !!activeIncident;

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border/70 bg-[#09090b]/90 backdrop-blur-md px-6 py-3.5">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        {/* Logo and Tagline */}
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-blue-500/20">
            <Shield className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-lg tracking-tight text-white">Sentinel<span className="text-blue-500">AI</span></span>
              <span className="px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20 text-[10px] font-mono font-medium">v1.0 Production Engine</span>
            </div>
            <p className="text-xs text-zinc-400 font-normal">Autonomous AI Reliability & Incident Response Platform</p>
          </div>
        </div>

        {/* Live System Status Pill */}
        <div className="flex items-center gap-4">
          <div className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full border text-xs font-mono font-medium ${
            isIncident 
              ? 'bg-red-500/10 border-red-500/30 text-red-400 animate-pulse' 
              : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
          }`}>
            <span className={`w-2 h-2 rounded-full ${isIncident ? 'bg-red-500' : 'bg-emerald-500'}`} />
            {isIncident ? 'INCIDENT IN PROGRESS' : 'PRODUCTION HEALTHY (SLO 99.9%)'}
          </div>

          {activeIncident?.pull_request && (
            <button
              onClick={onOpenPRModal}
              className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium font-mono transition-all shadow-md shadow-blue-600/30 hover:scale-[1.02]"
            >
              <GitPullRequest className="w-4 h-4" />
              <span>Review PR #{activeIncident.pull_request.pr_number}</span>
              <span className="px-1.5 py-0.5 rounded bg-blue-700 text-[10px]">Action Req</span>
            </button>
          )}
        </div>
      </div>
    </header>
  )
}
