import React, { useState, useEffect } from 'react'
import Navbar from './components/Navbar'
import MetricCards from './components/MetricCards'
import LiveCharts from './components/LiveCharts'
import ChaosControls from './components/ChaosControls'
import AgentTraceViewer from './components/AgentTraceViewer'
import PullRequestModal from './components/PullRequestModal'
import SafetyAuditLog from './components/SafetyAuditLog'

export default function App() {
  const [systemStatus, setSystemStatus] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [incidents, setIncidents] = useState([])
  const [auditLogs, setAuditLogs] = useState([])
  const [activeIncident, setActiveIncident] = useState(null)
  const [isPRModalOpen, setIsPRModalOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  // Fetch telemetry every 1.5s
  useEffect(() => {
    const fetchTelemetry = async () => {
      try {
        const [statusRes, metricsRes, incRes, auditRes] = await Promise.all([
          fetch('/api/status').then(r => r.json()),
          fetch('/api/metrics/live').then(r => r.json()),
          fetch('/api/incidents').then(r => r.json()),
          fetch('/api/audit-trail').then(r => r.json()),
        ])
        setSystemStatus(statusRes)
        setMetrics(metricsRes)
        setIncidents(incRes)
        setAuditLogs(auditRes)

        if (incRes.length > 0) {
          const latest = incRes[incRes.length - 1]
          setActiveIncident(latest)
        } else {
          setActiveIncident(null)
        }
      } catch (err) {
        console.error("Telemetry fetch error:", err)
      }
    }

    fetchTelemetry()
    const interval = setInterval(fetchTelemetry, 1500)
    return () => clearInterval(interval)
  }, [])

  const handleTriggerChaos = async (scenarioId) => {
    setLoading(true)
    try {
      const res = await fetch('/api/chaos/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario_id: scenarioId })
      }).then(r => r.json())
      
      // Auto-open PR modal after brief inspection
      setTimeout(() => {
        setIsPRModalOpen(true)
      }, 1800)
    } catch (err) {
      console.error("Chaos error:", err)
    } finally {
      setLoading(false)
    }
  }

  const handleReset = async () => {
    setLoading(true)
    try {
      await fetch('/api/chaos/reset', { method: 'POST' })
      setActiveIncident(null)
      setIsPRModalOpen(false)
    } catch (err) {
      console.error("Reset error:", err)
    } finally {
      setLoading(false)
    }
  }

  const handleApprovePR = async (incidentId, reviewerName) => {
    setLoading(true)
    try {
      const res = await fetch(`/api/incidents/${incidentId}/pr/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewer_name: reviewerName })
      }).then(r => r.json())

      if (res.incident) {
        setActiveIncident(res.incident)
      }
      setTimeout(() => {
        setIsPRModalOpen(false)
      }, 1200)
    } catch (err) {
      console.error("PR approval error:", err)
    } finally {
      setLoading(false)
    }
  }

  const handleRejectPR = async (incidentId, reviewerName) => {
    setLoading(true)
    try {
      const res = await fetch(`/api/incidents/${incidentId}/pr/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewer_name: reviewerName })
      }).then(r => r.json())

      if (res.incident) {
        setActiveIncident(res.incident)
      }
      setIsPRModalOpen(false)
    } catch (err) {
      console.error("PR reject error:", err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background text-zinc-100 flex flex-col">
      <Navbar
        systemStatus={systemStatus}
        activeIncident={activeIncident}
        onOpenPRModal={() => setIsPRModalOpen(true)}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-6 space-y-6">
        {/* Top KPI Metrics Cards */}
        <MetricCards
          metrics={metrics}
          systemStatus={systemStatus}
          activeIncident={activeIncident}
        />

        {/* Live Charts */}
        <LiveCharts timeseries={metrics?.timeseries} />

        {/* Chaos Engineering Studio */}
        <ChaosControls
          onTriggerChaos={handleTriggerChaos}
          onReset={handleReset}
          activeScenario={systemStatus?.active_chaos_scenario}
          loading={loading}
        />

        {/* Multi-Agent Reasoning Trace */}
        <AgentTraceViewer
          incident={activeIncident}
          onOpenPRModal={() => setIsPRModalOpen(true)}
        />

        {/* Safety Governance Audit Log */}
        <SafetyAuditLog auditLogs={auditLogs} />
      </main>

      {/* Pull Request Review & Diff Modal */}
      <PullRequestModal
        incident={activeIncident}
        isOpen={isPRModalOpen}
        onClose={() => setIsPRModalOpen(false)}
        onApprove={handleApprovePR}
        onReject={handleRejectPR}
        loading={loading}
      />
    </div>
  )
}
