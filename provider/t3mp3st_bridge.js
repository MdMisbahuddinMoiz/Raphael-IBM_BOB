#!/usr/bin/env node
/**
 * T3MP3ST Bridge — RAPHAEL-owned, minimal provider bridge for C1A.
 *
 * Imports ONLY the T3MP3ST binary_sink_scan handler directly
 * (`/t3mp3st/dist/arsenal/binary.js`), avoiding the full arsenal/CLI
 * dispatcher and its network-capable import chain.
 *
 * Contract:
 *   - Reads exactly one file: /fixture (RAPHAEL-mounted, read-only).
 *   - Emits exactly ONE bounded JSON receipt on stdout.
 *   - Emits ONLY non-authority fields: success, output, error, tool.
 *     The T3MP3ST `findings` array (severity/cwe/title/details) is
 *     deliberately EXCLUDED so no provider verdict can become RAPHAEL
 *     authority. The raw `output` text is preserved as untrusted evidence.
 *   - Echoes RAPHAEL-issued identity; invents none.
 *   - Executes exactly once.
 */

'use strict';

const MAX_OUTPUT_BYTES = 65536;
const FIXTURE_PATH = '/fixture';
const TOOL_NAME = 'binary_sink_scan';
const PROVIDER_MODULE = 'file:///t3mp3st/dist/arsenal/binary.js';

const RUN_ID = process.env.RAPHAEL_RUN_ID || '';
const INVOCATION_ID = process.env.RAPHAEL_INVOCATION_ID || '';

let executed = false;

function emit(receipt, ok) {
  let out = JSON.stringify(receipt);
  if (out.length > MAX_OUTPUT_BYTES) {
    out = JSON.stringify({
      success: false,
      output: '',
      error: 'bridge receipt exceeded output cap',
      tool: TOOL_NAME,
    });
    ok = false;
  }
  process.stdout.write(out);
  process.exit(ok ? 0 : 1);
}

function fail(code, message) {
  process.stderr.write(JSON.stringify({
    diagnostic: 't3mp3st_bridge_failure',
    run_id: RUN_ID,
    invocation_id: INVOCATION_ID,
    code: code,
    message: message,
  }));
  emit({ success: false, output: '', error: code + ': ' + message,
         tool: TOOL_NAME }, false);
}

async function main() {
  if (executed) {
    fail('duplicate_invocation', 'bridge already executed');
    return;
  }
  executed = true;

  if (!RUN_ID || !INVOCATION_ID) {
    fail('missing_identity', 'RAPHAEL identity values not provided');
    return;
  }
  if (!process.env.T3MP3ST_SOURCE_ROOT) {
    fail('missing_source_root', 'T3MP3ST_SOURCE_ROOT not set');
    return;
  }

  let mod;
  try {
    mod = await import(PROVIDER_MODULE);
  } catch (err) {
    fail('provider_import_failed', String(err && err.message));
    return;
  }
  const tool = mod.binarySinkScanTool;
  if (!tool || typeof tool.handler !== 'function') {
    fail('provider_handler_missing', 'binarySinkScanTool.handler not found');
    return;
  }

  let result;
  try {
    result = await tool.handler({ parameters: { path: FIXTURE_PATH } });
  } catch (err) {
    fail('provider_execution_failed', String(err && err.message));
    return;
  }

  const output = typeof result.output === 'string' ? result.output : '';
  const error = typeof result.error === 'string' ? result.error : '';
  process.stderr.write(JSON.stringify({
    diagnostic: 't3mp3st_bridge_completed',
    run_id: RUN_ID,
    invocation_id: INVOCATION_ID,
    tool: TOOL_NAME,
    success: result.success === true,
  }));

  emit({
    success: result.success === true,
    output: output.slice(0, MAX_OUTPUT_BYTES),
    error: error,
    tool: TOOL_NAME,
  }, result.success === true);
}

main();
