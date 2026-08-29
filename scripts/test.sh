#!/usr/bin/env bash
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "================================================================="
echo "  Running SentinelAI Reliability & Multi-Agent Test Suite"
echo "================================================================="

.venv/bin/pytest tests/ -v --tb=short
