# T3MP3ST Integration

This document records the real-provider C1A integration: replacing the
"provider unavailable" boundary with the ACTUAL pinned T3MP3ST
implementation while preserving every RAPHAEL authority invariant.

## Pinned revisions

| Item | Value |
|------|-------|
| T3MP3ST provider revision | `29824d5625ede419ac8cdae418c8f4c72c6270f7` |
| RAPHAEL `PROVIDER_PIN` | `29824d5625ede419ac8cdae418c8f4c72c6270f7` (matches) |
| Node requirement (T3MP3ST `engines`) | `>=22.19.0` |
| Observed Node | `v22.22.1` |
| Bridge pin (`provider/t3mp3st_bridge.js`) | `ea5616e1515004fe2fed344eb6787ed29d57a6040e0290ad3069321799056101` |

The provider source is mounted READ-ONLY and is never modified.

## Canonical execution path

One path only:

```
RAPHAEL
  -> bwrap sandbox
    -> RAPHAEL-owned bridge (provider/t3mp3st_bridge.js)
      -> binarySinkScanTool.handler()   (direct handler)
```

The bridge imports ONLY the compiled `dist/arsenal/binary.js` direct
handler. The full CLI/arsenal dispatcher is deliberately NOT used: the
handler's compiled import closure is Node builtins (`fs`, `path`) plus its
sibling `local-file-scope.js`, so no `node_modules` and no network-capable
import chain is pulled in. Verified from the compiled `dist/arsenal/binary.js`:

```
import { readFileSync, statSync, readdirSync } from 'fs';
import { join } from 'path';
import { approvedLocalPath } from './local-file-scope.js';
```

## Bridge contract

- Reads exactly one file: `/fixture` (the RAPHAEL-mounted fixture).
- Emits exactly one bounded JSON receipt on stdout:
  `{success, output, error, tool}`.
- **Excludes** T3MP3ST's `findings` array
  (`severity`/`cwe`/`title`/`details`) so no provider verdict can become
  RAPHAEL authority. The raw `output` text is preserved as UNTRUSTED
  `provider_message`.
- Echoes RAPHAEL-issued `RAPHAEL_RUN_ID` / `RAPHAEL_INVOCATION_ID`.
- Executes exactly once.

## Sandbox (`build_t3mp3st_bwrap_argv`)

Read-only mounts:

| Mount | Destination |
|-------|-------------|
| each Node runtime closure path (individually) | same path |
| `<provider_dist>` | `/t3mp3st/dist` |
| `provider/t3mp3st_bridge.js` | `/provider/t3mp3st_bridge.js` |
| exact fixture file | `/fixture` |
| `/etc/ld.so.cache` | `/etc/ld.so.cache` |

Isolation: `--unshare-user --unshare-pid --unshare-ipc --unshare-uts
--unshare-net --die-with-parent --new-session --cap-drop ALL --uid 65534
--gid 65534 --remount-ro / --clearenv`, then `T3MP3ST_SOURCE_ROOT=/fixture`.
No whole-tree binds (no `/usr/lib`, no `/lib`).

`--remount-ro /` is what actually enforces the read-only root: without it
bwrap leaves `/` writable (observed). With it, writes to `/` and `/fixture`
fail with `EROFS`. `/tmp` is not mounted, so it is not writable; the
sandbox therefore has no writable filesystem at all. (The earlier claim
that `/tmp` is "noexec" is NOT made: no per-mount `noexec` flag is set,
because no tmpfs is mounted.)

## Observed path validation (real `approvedLocalPath`)

| Case | Result |
|------|--------|
| root `/fixture` | accepted |
| valid child | accepted |
| sibling prefix `/fixture_evil/...` | rejected |
| traversal `/fixture/../...` | rejected |
| outside path | rejected |
| `fixture_evil` | rejected |

## Authority mapping

| T3MP3ST field | RAPHAEL ProviderResult | Authority? | Action |
|---------------|------------------------|-----------|--------|
| `success` | `state` (SUCCESS/FAILURE) | no | map |
| `output` | `provider_message` (bounded) | no | extract |
| `error` | `error` (bounded) | no | extract |
| `findings[].severity` | — | yes | EXCLUDED + rejected |
| `findings[].cwe` | — | yes | EXCLUDED + rejected |
| `findings[].title` | — | yes | EXCLUDED + rejected |
| `findings[].details` | — | yes | EXCLUDED + rejected |

`result_hash` is a deterministic SHA-256 of the bounded provider output. It
is UNTRUSTED metadata used so an INDEPENDENT reproduction can be compared
by digest — never by matching an authority string.

## Verification semantics

C1A verification (`c1a_verification`) transitions `UNVERIFIED -> VERIFIED`
only when an INDEPENDENT reproduction succeeds AND its provider
`result_hash` equals the expected digest. Provider success alone is never
sufficient, and no output text is turned into VERIFIED by string matching.

## Status

- `provider_execution = VERIFIED` (real provider ran in the sandbox, local).
- `live_proof_authorized = FALSE` (unchanged).
- M1 / M2 / M5 = **NOT VERIFIED**; seccomp = `NOT_EXECUTED`.
- The live proof remains BLOCKED.
