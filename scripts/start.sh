#!/usr/bin/env bash
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "================================================================="
echo "  🛡️  SentinelAI — Autonomous AI Reliability & Incident Response "
echo "      Detect → Diagnose → Propose → Validate → Human Review     "
echo "================================================================="

export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_NOSYSTEM=1

echo "[1/2] Starting SentinelAI FastAPI Backend on http://localhost:8000..."
.venv/bin/python -m uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

echo "[2/2] Starting Mission Control Dashboard on http://localhost:5173..."
cd dashboard
npm run dev &
FRONTEND_PID=$!

cleanup() {
    echo ""
    echo "[INFO] Stopping SentinelAI services..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

echo ""
echo "🚀 SentinelAI is LIVE!"
echo "   -> Mission Control Dashboard: http://localhost:5173"
echo "   -> REST API / Swagger Docs:  http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all services."
wait
