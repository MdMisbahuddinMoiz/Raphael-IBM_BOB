#!/usr/bin/env node
/**
 * C1A Launcher — single-purpose, non-authoritative sandbox launcher.
 *
 * CONTRACT:
 *   - Reads exactly ONE file: the RAPHAEL-supplied fixture literal.
 *   - Emits exactly ONE bounded JSON receipt on stdout.
 *   - No network, no child processes, no dynamic code execution, no shell.
 *   - Echoes RAPHAEL-issued identity values; it never invents authoritative
 *     identity.
 *   - The receipt uses the CLOSED provider schema keys only:
 *       results, artifacts, operation_id, result_hash,
 *       provider_message, truncated
 *     It never emits authority fields (verdict/verified/complete/...).
 *   - Executes exactly once per process.
 */

'use strict';

const fs = require('fs');
const crypto = require('crypto');

const MAX_OUTPUT_BYTES = 65536;
const MAX_RESULTS = 64;
const MAX_FIXTURE_BYTES = 1048576;
const TOOL_NAME = 'binary_sink_scan';

// RAPHAEL-issued identity (echoed, never fabricated).
const RUN_ID = process.env.RAPHAEL_RUN_ID || '';
const INVOCATION_ID = process.env.RAPHAEL_INVOCATION_ID || '';
const PROOF_SESSION_ID = process.env.RAPHAEL_PROOF_SESSION_ID || '';
const FIXTURE_PATH = process.env.RAPHAEL_FIXTURE_PATH || '';

let executed = false;

function withinPath(value) {
  return typeof value === 'string'
    && value.length > 0
    && value.indexOf('\u0000') === -1
    && value.indexOf('..') === -1;
}

function emit(receipt, ok) {
  let output = JSON.stringify(receipt);
  if (output.length > MAX_OUTPUT_BYTES) {
    output = JSON.stringify({
      results: [],
      artifacts: [],
      operation_id: receipt.operation_id || null,
      result_hash: null,
      truncated: true,
      provider_message: 'receipt exceeded output cap',
    });
    ok = false;
  }
  process.stdout.write(output);
  process.exit(ok ? 0 : 1);
}

function fail(message) {
  process.stderr.write(JSON.stringify({
    diagnostic: 'launcher_failure',
    run_id: RUN_ID,
    invocation_id: INVOCATION_ID,
    message: message,
  }));
  emit({
    results: [],
    artifacts: [],
    operation_id: INVOCATION_ID ? INVOCATION_ID + '-failed' : null,
    result_hash: null,
    truncated: false,
    provider_message: message,
  }, false);
}

function scan(data) {
  const results = [];
  // Deterministic binary-sink heuristics over the exact bytes (latin1 maps
  // bytes 1:1 to code points, so offsets are byte offsets).
  const text = data.toString('latin1');
  const patterns = [
    ['nul_run', /\u0000{2,}/g],
    ['open_concat', /open\s*\(\s*[^)]*\+\s*\w+/g],
    ['binary_write', /\.write\s*\(\s*bytes\s*\(/g],
    ['dynamic_exec', /\b(eval|exec)\s*\(/g],
  ];
  for (const entry of patterns) {
    const kind = entry[0];
    const pattern = entry[1];
    pattern.lastIndex = 0;
    let match = pattern.exec(text);
    while (match !== null) {
      results.push({
        path: FIXTURE_PATH,
        kind: kind,
        offset: match.index,
        size: match[0].length,
      });
      if (results.length >= MAX_RESULTS) {
        return results;
      }
      match = pattern.exec(text);
    }
  }
  return results;
}

function main() {
  if (executed) {
    fail('duplicate_invocation');
    return;
  }
  executed = true;

  if (!RUN_ID || !INVOCATION_ID || !PROOF_SESSION_ID) {
    fail('missing_identity');
    return;
  }
  if (!withinPath(FIXTURE_PATH) || FIXTURE_PATH[0] !== '/') {
    fail('invalid_fixture_path');
    return;
  }

  let data;
  try {
    const stat = fs.statSync(FIXTURE_PATH);
    if (!stat.isFile()) {
      fail('fixture_not_regular_file');
      return;
    }
    if (stat.size > MAX_FIXTURE_BYTES) {
      fail('fixture_over_size_cap');
      return;
    }
    data = fs.readFileSync(FIXTURE_PATH);
  } catch (err) {
    fail('fixture_unreadable');
    return;
  }

  const fixtureHash = crypto.createHash('sha256').update(data).digest('hex');
  const scanned = scan(data);
  const truncated = scanned.length >= MAX_RESULTS;

  process.stderr.write(JSON.stringify({
    diagnostic: 'launcher_completed',
    run_id: RUN_ID,
    proof_session_id: PROOF_SESSION_ID,
    tool: TOOL_NAME,
    fixture_size: data.length,
  }));

  emit({
    results: scanned.map((r) => ({
      path: FIXTURE_PATH,
      kind: r.kind,
      offset: r.offset,
      size: r.size,
      hash: 'sha256:' + fixtureHash,
    })),
    artifacts: [],
    operation_id: INVOCATION_ID + '-op',
    result_hash: 'sha256:' + fixtureHash,
    truncated: truncated,
    provider_message: 'launcher_completed',
  }, true);
}

main();
