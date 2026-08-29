import React from 'react'
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid, LineChart, Line } from 'recharts'
import { Activity, DollarSign, Award } from 'lucide-react'

export default function LiveCharts({ timeseries }) {
  const data = (timeseries && timeseries.length > 0) ? timeseries.slice(-30) : []

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* Latency & Retrieval Timeline */}
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-blue-400" />
            <h3 className="text-sm font-semibold text-zinc-200">Real-Time Latency & Retrieval Trends</h3>
          </div>
          <div className="flex items-center gap-3 text-xs font-mono">
            <span className="flex items-center gap-1 text-blue-400">
              <span className="w-2 h-2 rounded-full bg-blue-500 inline-block" /> p95 Latency (s)
            </span>
            <span className="flex items-center gap-1 text-indigo-400">
              <span className="w-2 h-2 rounded-full bg-indigo-500 inline-block" /> p50 Latency (s)
            </span>
          </div>
        </div>

        <div className="h-48 w-full font-mono text-xs">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="latencyGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4}/>
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis dataKey="time_formatted" stroke="#71717a" fontSize={10} tickLine={false} />
              <YAxis stroke="#71717a" fontSize={10} domain={[0, 'auto']} tickLine={false} />
              <Tooltip
                contentStyle={{ backgroundColor: '#18181b', borderColor: '#3f3f46', borderRadius: '8px', fontSize: '11px' }}
                labelStyle={{ color: '#a1a1aa' }}
              />
              <Area type="monotone" dataKey="p95_latency" stroke="#3b82f6" strokeWidth={2} fillOpacity={1} fill="url(#latencyGradient)" name="p95 Latency" />
              <Line type="monotone" dataKey="p50_latency" stroke="#818cf8" strokeWidth={1.5} dot={false} name="p50 Latency" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Cost vs Groundedness Quality */}
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-zinc-200">Cost per Request & RAG Faithfulness</h3>
          </div>
          <div className="flex items-center gap-3 text-xs font-mono">
            <span className="flex items-center gap-1 text-emerald-400">
              <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" /> Avg Cost ($)
            </span>
            <span className="flex items-center gap-1 text-amber-400">
              <span className="w-2 h-2 rounded-full bg-amber-500 inline-block" /> Groundedness (%)
            </span>
          </div>
        </div>

        <div className="h-48 w-full font-mono text-xs">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis dataKey="time_formatted" stroke="#71717a" fontSize={10} tickLine={false} />
              <YAxis yAxisId="left" stroke="#71717a" fontSize={10} tickLine={false} domain={[0, 0.20]} />
              <YAxis yAxisId="right" orientation="right" stroke="#71717a" fontSize={10} tickLine={false} domain={[60, 100]} />
              <Tooltip
                contentStyle={{ backgroundColor: '#18181b', borderColor: '#3f3f46', borderRadius: '8px', fontSize: '11px' }}
                labelStyle={{ color: '#a1a1aa' }}
              />
              <Line yAxisId="left" type="monotone" dataKey="avg_cost" stroke="#10b981" strokeWidth={2} dot={false} name="Cost ($/req)" />
              <Line yAxisId="right" type="monotone" dataKey="avg_groundedness" stroke="#f59e0b" strokeWidth={2} dot={false} name="Groundedness (%)" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
