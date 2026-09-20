#!/usr/bin/env bash
# ==============================================================================
# RAPHAEL IBM BOB — Canonical Judge Demonstration Runner
#
# Usage:
#   ./scripts/run_demo.sh            # Run canonical governed demo (exit 0, COMPLETE)
#   ./scripts/run_demo.sh --refuse   # Run refusal scenario (exit 1, REFUSE)
#   ./scripts/run_demo.sh --check-prereqs # Check environment prerequisites
#   ./scripts/run_demo.sh --help     # Display usage options
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Ensure we operate within the repository root
cd "${REPO_ROOT}"

# Check for Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required but not found in PATH." >&2
    exit 2
fi

# Execute canonical hero demo with repository root in PYTHONPATH
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"
exec python3 "${REPO_ROOT}/demos/canonical_hero.py" "$@"
