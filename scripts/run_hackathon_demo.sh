#!/usr/bin/env bash
# ==============================================================================
# RAPHAEL x IBM BOB - Hackathon Demo Runner (canonical entrypoint)
#
# Drives the REAL product HTTP API (the same endpoints the operator UI uses)
# and reads the persisted run ledger. It NEVER bypasses the server, the
# Broker/Policy boundary, or the QualityGate, and never fabricates evidence.
#
# Usage:
#   ./scripts/run_hackathon_demo.sh --status      # environment + recent runs
#   ./scripts/run_hackathon_demo.sh --preflight   # READY / NOT READY / OPTIONAL
#   ./scripts/run_hackathon_demo.sh --success     # governed run -> 7/7 COMPLETE
#   ./scripts/run_hackathon_demo.sh --refuse      # honest refusal -> REFUSE
#   ./scripts/run_hackathon_demo.sh --tests       # one-command release suite
#   ./scripts/run_hackathon_demo.sh --help
#
# Exit codes:
#   --success : 0 = COMPLETE, 1 = REFUSE (unexpected), 2 = environment error
#   --refuse  : 0 = REFUSE   (honest),  1 = COMPLETE (dangerous), 2 = env error
#   --tests   : 0 = all pass, non-zero = failures
#   --preflight: 0 = READY, 2 = NOT READY
#
# Overridable environment:
#   RAPHAEL_BASE_URL, RAPHAEL_TARGET_HOST, RAPHAEL_TARGET_PORT,
#   RAPHAEL_REQUEST_PATH, RAPHAEL_PROBE_PATH, RAPHAEL_MISSION_ID
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

# The release suite: D7/D8/D9/D9.1/D9.2/D10.1/D10.2 + HTTP/API/UI + D11 assertions.
RELEASE_SUITES=(
  tests.test_d7_vpn
  tests.test_d8_mode
  tests.test_d9_network
  tests.test_d9_1_network_run
  tests.test_d9_2_gate_presentation
  tests.test_d10_1_network_gate
  tests.test_d10_2_network_probe
  tests.test_m6_quality_gate
  tests.test_m2_boundary
  tests.test_seam_contracts
  tests.test_harness
  tests.test_m13_harness
  tests.test_m15_1_http_api
  tests.test_m15_2_parity
  tests.test_m15_3_decision_trace
  tests.test_m15_4_live_stream
  tests.test_m15_5_event_stream_page
  tests.test_m15_6_command_center
  tests.test_d11_release_assertions
)

usage() {
  sed -n '2,33p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

MODE="${1:---help}"
case "${MODE}" in
  --status|--preflight|--success|--refuse)
    command -v python3 >/dev/null 2>&1 || {
      echo "ERROR: python3 is required but not found in PATH." >&2; exit 2; }
    exec python3 "${SCRIPT_DIR}/hackathon_demo.py" "${MODE}"
    ;;
  --tests)
    command -v python3 >/dev/null 2>&1 || {
      echo "ERROR: python3 is required but not found in PATH." >&2; exit 2; }
    echo "RAPHAEL x IBM BOB - release suite (${#RELEASE_SUITES[@]} modules)"
    exec python3 -m unittest "${RELEASE_SUITES[@]}"
    ;;
  --help|-h|"")
    usage
    ;;
  *)
    echo "ERROR: unknown option '${MODE}'" >&2
    echo >&2
    usage >&2
    exit 2
    ;;
esac
