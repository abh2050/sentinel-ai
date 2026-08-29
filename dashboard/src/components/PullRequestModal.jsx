import React, { useState } from 'react'
import { X, GitPullRequest, GitBranch, CheckCircle2, ShieldAlert, FileCode2, ArrowRight, UserCheck, XCircle } from 'lucide-react'

export default function PullRequestModal({ incident, isOpen, onClose, onApprove, onReject, loading }) {
  if (!isOpen || !incident || !incident.pull_request) return null

  const pr = incident.pull_request
  const val = incident.validation
  const diag = incident.diagnosis
  const [reviewerName, setReviewerName] = useState("Lead SRE Engineer")

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn">
      <div className="relative w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-2xl border border-zinc-700 bg-[#101014] p-6 shadow-2xl shadow-black/80 text-zinc-100">
        
        {/* Modal Header */}
        <div className="flex items-center justify-between pb-4 border-b border-zinc-800">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-blue-600/20 border border-blue-500/30 text-blue-400">
              <GitPullRequest className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-semibold text-blue-400">Pull Request #{pr.pr_number}</span>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono border ${
                  pr.status === 'MERGED' 
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' 
                    : 'bg-blue-500/10 text-blue-400 border-blue-500/30'
                }`}>
                  {pr.status}
                </span>
              </div>
              <h2 className="text-base font-bold text-white mt-0.5">{pr.title}</h2>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close pull request review"
            className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* PR Metadata Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 my-4 p-3 rounded-xl bg-zinc-900/60 border border-zinc-800 text-xs font-mono">
          <div>
            <span className="text-zinc-500 block text-[10px]">BRANCH</span>
            <span className="text-zinc-200 flex items-center gap-1 mt-0.5">
              <GitBranch className="w-3.5 h-3.5 text-blue-400" /> {pr.branch_name}
            </span>
          </div>
          <div>
            <span className="text-zinc-500 block text-[10px]">INCIDENT</span>
            <span className="text-zinc-200 font-semibold">{incident.incident_id}</span>
          </div>
          <div>
            <span className="text-zinc-500 block text-[10px]">AUTHOR</span>
            <span className="text-zinc-200">SentinelAI Agent</span>
          </div>
          <div>
            <span className="text-zinc-500 block text-[10px]">GOVERNANCE</span>
            <span className="text-amber-400 font-semibold">Human Approval Req</span>
          </div>
        </div>

        {/* Validation Scorecard Comparison Table */}
        <div className="mb-4">
          <h3 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider mb-2 flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Sandbox Validation Scorecard
          </h3>
          <div className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-900/40">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-zinc-800/60 text-zinc-400 text-[11px]">
                <tr>
                  <th className="py-2.5 px-3">Metric</th>
                  <th className="py-2.5 px-3">During Incident</th>
                  <th className="py-2.5 px-3">After Sandbox Fix</th>
                  <th className="py-2.5 px-3">Improvement</th>
                  <th className="py-2.5 px-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {val?.metric_comparisons?.map((m, i) => (
                  <tr key={i} className="hover:bg-zinc-800/20">
                    <td className="py-2 px-3 text-zinc-300 font-medium">{m.metric_name}</td>
                    <td className="py-2 px-3 text-red-400">{m.before_value}</td>
                    <td className="py-2 px-3 text-emerald-400 font-semibold">{m.after_value}</td>
                    <td className="py-2 px-3 text-blue-400">{m.improvement}</td>
                    <td className="py-2 px-3">
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        {m.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Code Diff Viewer */}
        <div className="mb-4">
          <h3 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider mb-2 flex items-center gap-2">
            <FileCode2 className="w-4 h-4 text-blue-400" /> Proposed Surgical Code & Config Patch
          </h3>
          <div className="p-3.5 rounded-lg bg-black border border-zinc-800 font-mono text-xs overflow-x-auto text-zinc-300 leading-relaxed">
            <div className="text-zinc-500 text-[11px] mb-1">--- a/rag_service/config.py<br/>+++ b/rag_service/config.py</div>
            <div className="text-red-400 bg-red-950/20 px-2 py-0.5 rounded">-    top_k: int = Field(default=30, description="Number of chunks retrieved from vector store")</div>
            <div className="text-emerald-400 bg-emerald-950/20 px-2 py-0.5 rounded">+    top_k: int = Field(default=8, description="Number of chunks retrieved from vector store")</div>
            <div className="text-zinc-400 px-2 py-0.5">     similarity_threshold: float = Field(default=0.68)</div>
            <div className="text-red-400 bg-red-950/20 px-2 py-0.5 rounded">-    reranker_enabled: bool = Field(default=False)</div>
            <div className="text-emerald-400 bg-emerald-950/20 px-2 py-0.5 rounded">+    reranker_enabled: bool = Field(default=True, description="Enable cross-encoder reranking")</div>
            <div className="text-emerald-400 bg-emerald-950/20 px-2 py-0.5 rounded">+    reranker_top_n: int = Field(default=5, description="Top-5 most relevant chunks")</div>
          </div>
        </div>

        {/* Safety Covenant Notice */}
        <div className="p-3.5 rounded-xl bg-amber-950/20 border border-amber-500/30 text-xs text-amber-200 mb-6 flex items-start gap-3">
          <ShieldAlert className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          <div>
            <span className="font-bold block text-amber-300">Mandatory Human-in-the-Loop Gate</span>
            <span>SentinelAI policy prevents autonomous direct merge to production. Reviewing and clicking "Approve & Merge" records your human audit signature and deploys the fix to live production.</span>
          </div>
        </div>

        {/* Reviewer Actions */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-4 border-t border-zinc-800">
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <span className="text-xs text-zinc-400 font-mono">Reviewer:</span>
            <input
              type="text"
              value={reviewerName}
              onChange={(e) => setReviewerName(e.target.value)}
              className="px-2.5 py-1.5 rounded-lg bg-zinc-900 border border-zinc-700 text-xs text-zinc-200 font-mono focus:border-blue-500 focus:outline-none"
              placeholder="Your Name (e.g. Lead SRE)"
            />
          </div>

          <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
            <button
              onClick={() => onReject(incident.incident_id, reviewerName)}
              disabled={loading || pr.status === 'MERGED'}
              className="px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-mono font-medium border border-zinc-700 transition-colors flex items-center gap-1.5"
            >
              <XCircle className="w-4 h-4 text-red-400" />
              Reject Patch
            </button>

            <button
              onClick={() => onApprove(incident.incident_id, reviewerName)}
              disabled={loading || pr.status === 'MERGED'}
              className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-mono font-semibold transition-all shadow-lg shadow-emerald-600/30 flex items-center gap-2 hover:scale-[1.02]"
            >
              <UserCheck className="w-4 h-4" />
              {pr.status === 'MERGED' ? 'Merged & Deployed ✓' : 'Approve & Merge to Main →'}
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
