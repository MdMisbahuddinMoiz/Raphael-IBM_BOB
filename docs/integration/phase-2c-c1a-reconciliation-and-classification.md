# Phase 2C — C1/C1A Reconciliation, Class A/B Inventory, and execve Semantics

Status: tracked reconciliation note. Authoring base HEAD:
`780f9bd99cf5973d61b1eba03316a30175202fac`.

This note closes the forensic findings **F3** (capability/naming/scope drift),
**F4** (`RUN_TEST` classification), and **F5** (seccomp `execve`
documentation mismatch). It does **not** implement C1A, does not execute any
provider, and does not modify the historical untracked document
`docs/integration/phase-2b-delta-hardening.md` (left exactly as authored).

---

## 1. F3 — historical `C1` vs operative `C1A` (different audit subjects)

The historical, pre-2C hardening document
`docs/integration/phase-2b-delta-hardening.md` audited a **different**
capability/tool than the operative Phase 2C C1A capability. It must **not** be
read as the operative C1A capability definition.

| dimension | historical delta document | operative Phase 2C C1A |
|---|---|---|
| capability name | `C1 static_file_manifest` | `C1A static_file_inspect` |
| provider | T3MP3ST **`file`** catalog adapter | T3MP3ST **`binary_sink_scan`** |
| provider source | `src/arsenal/catalog.ts` + `adapter-tools.ts` (`runSubprocess` → `execFile('file', …)`) | `src/arsenal/binary.ts` (`binarySinkScanTool`) |
| execution primitive | subprocess (`execFile`) | **pure JS** (`readFileSync` + regex) |
| conclusion recorded | "C1 NOT APPLICABLE" (subprocess dependency) | Class A candidate (execution-free) |

Key distinction: the delta document's "C1 NOT APPLICABLE" verdict was reached
for the **`file` adapter**, which shells out to the external `file(1)` binary.
It does **not** apply to `binary_sink_scan`, which is implemented entirely in
JavaScript: `readFileSync` → printable-string extraction → regex rule matching,
bounded to 10 MiB, with `approvedLocalPath` scope enforcement
(`realpathSync`/`statSync`, no subprocess). History is not rewritten; the two
are simply different audit subjects.

Operative identifiers (source of truth, `raphael_ibm_bob/provider_runtime.py`):

```
C1A_CAPABILITY_ID = "C1A static_file_inspect"
C1A_PROVIDER_ID   = "t3mp3st"
C1A_TOOL          = "binary_sink_scan"
```

Provider pin: `elder-plinius/T3MP3ST@29824d5625ede419ac8cdae418c8f4c72c6270f7`
(working tree clean at audit time).

---

## 2. F4 — Class A / Class B / `RUN_TEST` classification (frozen)

`RUN_TEST` is **GOVERNED UNSANDBOXED HOST EXECUTION**. It is:

- **NOT** Class A (it is not execution-free);
- **NOT** sandboxed Class B (it does not run under the M2 isolation substrate);
- **NOT** Phase 2C isolation execution;
- **NOT** C1A provider execution.

Composition (governed, but content-unconstrained at the capability layer):

```
WRITE(target, purpose="content=<arbitrary text>")   capabilities.py:62 (_write)
        +
RUN_TEST(target)  where target matches test_*.py / *_test.py
        =
host `python3 -m unittest <module>` execution       capabilities.py:75 (_run_test) -> subprocess.run
```

Frozen facts:

- Broker/Policy gating exists: every `RUN_TEST` still traverses
  `Runtime → Broker → Policy`; the Broker is the sole caller of
  `execute_capability` (`raphael_ibm_bob/broker.py:222`).
- Workspace/path constraints exist: `Policy` requires the target to resolve
  inside the declared `Workspace` and match the `test_*.py` / `*_test.py`
  shape (`raphael_ibm_bob/policy.py:118`).
- The execution is nevertheless **host-side**: `subprocess.run` executes on
  the RAPHAEL host, not inside the bwrap/M2 sandbox.
- Environment/network are inherited: the child receives `dict(os.environ)`
  (including any credentials) and the host network path.
- `RUN_TEST` is **outside Class A** and **outside C1A**.
- **No stronger structural isolation is claimed.** Because `RUN_TEST` executes
  arbitrary host Python under the workspace/Policy constraints, the executed
  code can `import` and use available RAPHAEL modules (including
  `raphael_ibm_bob.provider_runtime` / `raphael_ibm_bob.adapters`). There is,
  however, **no current provider transport**: `ProviderRuntime.invoke_governed`
  is not wired to any runtime entry point, and `T3MP3STAdapter.invoke` fails
  closed with `ProviderUnavailableError`. `RUN_TEST` therefore cannot currently
  realize a provider invocation — but that is an **availability fact (transport
  absent), not a structural guarantee enforced by `RUN_TEST`**. Documentation
  must not assert a stronger isolation property than the code enforces.

| capability | class | execution primitive | network | filesystem | authority | provider | status |
|---|---|---|---|---|---|---|---|
| `read` / `list` / `search` / `write` | A | pure Python | none | workspace | Policy | native | wired |
| `binary_sink_scan` | A (candidate) | pure JS `readFileSync`+regex | none | read-only fixture | none | t3mp3st | not wired (adapter refuses) |
| `run_test` | **governed unsandboxed host** | `subprocess.run` | host | workspace | Policy | native | wired |
| future sandbox Class B | B | pinned binary under M2 isolation | netns-denied | ro-only | Policy | provider | not implemented |

---

## 3. F5 — actual seccomp `execve` semantics

The implementation is the source of truth (`raphael_ibm_bob/seccomp_policy.py`):

- `execve` **allowed** — required so `bwrap` can `exec` the pinned runtime
  after applying the filter (`CURATED_ALLOWLIST`, "loader").
- `execveat` **denied** (`DENIED_SYSCALLS`).
- Arbitrary child-process creation is constrained by the **argument-filtered
  `clone` rule**, not by `execve`:
  `(flags & (CLONE_VM|CLONE_THREAD|CLONE_NEWMASK_FULL)) == CLONE_VM|CLONE_THREAD`
  (thread-only clones allowed; fork-like clones and every `CLONE_NEW*` bit
  rejected), with `clone3 → ENOSYS` so glibc falls back to the filtered
  `clone`. JS-reachable `child_process` therefore fails with `EPERM`
  (observed in the G2 negative smoke).
- No shell path exists in Class A: `binary_sink_scan` is pure JS; no
  shell/tmux/subprocess is exposed by the C1A capability.
- The sandbox runtime closure remains explicitly curated (31 individually
  read-only-bound paths).

Correction applied to the historical design wording in
`docs/integration/phase-2c-isolation-engineering-design.md` (§4 SECURITY):
the previous "deny … `execve` beyond node" phrasing is replaced with the
actual semantics above.

---

## 4. Authority invariants (unchanged, restated)

This note grants no authority. Broker/Policy remains the sole
authorization authority; the Quality Gate remains the sole COMPLETE
authority; lifecycle attestation is not authorization, verification, or
completion; provider results are not verified findings.
