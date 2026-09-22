# D12 — Governed Telnet Capability for HTB Meow (Live Run Report)

**Baseline:** frozen D1–D11 release `a8bd06b5c` (unchanged). D12 is the ONLY new
capability (POST-HACKATHON, additive).
**Target:** `10.129.223.207` TCP/23 (HTB Starting Point "Meow", Telnet)
**Revalidated live run ID:** `20260922T194600_63aa87` (correction run)
**Earlier run (superseded):** `20260922T193147_4e0196`
**VPN:** `starting_points_us-starting-point-2-dhcp.ovpn` → `tun0 10.10.15.172`
**Mode:** `TESTING / HTB` · **TargetProfile:** `TP-b957ec027e737e0d`
**Result:** raw flag captured from the live target · Finding **VERIFIED** ·
QualityGate **COMPLETE (7/7)**

> The flag **value** is intentionally omitted everywhere. Only hashes are
> recorded: raw-candidate SHA-256 `a869860b…ffbe`; HTB-submission
> (`HTB{<raw>}`) SHA-256 `75fd47dd…fb23`. The SHA-256 is **not** the flag.

---

## 1. Files changed (all additive; no D1–D11 semantics weakened)

| File | Change |
|---|---|
| `raphael_ibm_bob/contracts.py` | added `Capability.NETWORK_TELNET_SESSION` (HTTP capability untouched) |
| `raphael_ibm_bob/network_scope.py` | added `parse_telnet_target()` (HTTP parser untouched) |
| `raphael_ibm_bob/target_profile.py` | added `"telnet"` to `ALLOWED_PROTOCOLS` |
| `raphael_ibm_bob/telnet_runtime.py` | **new** — the only Telnet-I/O boundary + verifier |
| `raphael_ibm_bob/policy.py` | added `NETWORK_TELNET_SESSION` allow-list + `_consult_telnet()` |
| `raphael_ibm_bob/broker.py` | added `_execute_telnet()` path + `telnet_mediator` |
| `raphael_ibm_bob/quality_gate.py` | condition **E** applies the existing TargetProfile scope rule to the Telnet cap (no new condition, no semantics change) |
| `raphael_ibm_bob/harness/telnet_run.py` | **new** — deterministic governed Telnet mission |
| `raphael_ibm_bob/harness/api.py` | `start_network_run` dispatches Telnet vs HTTP by mission |
| `tests/test_d12_telnet.py` | **new** — 24 focused unit tests |
| `tests/test_d12_telnet_live.py` | **new** — live test, skipped unless `RAPHAEL_LIVE_MEOW=1` |
| `tests/test_seam_contracts.py` | capability allow-list expectation extended (additive) |

No SMB/SSH/shell/privesc/scanning was introduced. `NETWORK_HTTP_REQUEST`,
Broker/Policy mediation, the ledger, and the QualityGate are unchanged.

## 2. Capability schema

`TelnetSessionSpec` (mission-declared, structured):

```
target, port, username, password (EXPLICIT, may be ""), commands,
flag_command, flag_pattern, probe_command, negative_control_command,
timeout_seconds, purpose
```

For Meow: `username="root"`, `password=""` (explicit), `commands=[pwd, ls, cat flag.txt]`,
`flag_command="cat flag.txt"`, `flag_pattern="[0-9a-f]{32}"`. The password value is
never persisted; evidence records `auth_decision`, `authenticated`, `username`.

## 3. TargetProfile changes

Minimal: `ALLOWED_PROTOCOLS = ("http","https","telnet")`. Authorization stays
exact per protocol via the existing `TargetProfile.allows(host, port, protocol)`
(exact host match + exact port + exact protocol + non-empty authorization ref).
Meow: `locator=10.129.223.207`, `allowed_ports=[23]`, `allowed_protocols=["telnet"]`.

## 4. Telnet mediator design (`telnet_runtime.py`)

- Direct socket / Telnet protocol (IAC negotiation refused), **no** `telnetlib`,
  **no** subprocess, **no** shell, **no** redirects.
- Bounded: session timeout, total-byte cap, per-command fresh read buffer.
- One session per invocation; deterministic invocation id `TEL-<sha256>`.
- HMAC-bound invocation identity + `TelnetReplayGuard` (replay → DENY).
- Per-command `output_sha256`; output is `provider_untrusted`.
- Auth failure / refusal / timeout is **never** success.

## 5. Command allow-list

Global: `pwd`, `ls`, `cat flag.txt` (optional `cat /root/flag.txt` only if the
mission authorizes it). Rejected: `bash/sh/sudo/su/nc/curl/wget/python/perl/ruby/
ssh/telnet/...`, pipes, redirection, chaining, substitution, and all shell
metacharacters. Enforced in **both** Policy (fail-closed, before any session)
and the mediator.

## 6. Evidence structure (producer `telnet`)

```
payload.telnet_result = {
  state, invocation_id, mission_id, target_id, host, port, protocol,
  username, authenticated, auth_decision, session_bytes,
  commands:[{command, output_sha256, output_preview, bytes, ok}],
  flag, flag_sha256, flag_command, error, provider_untrusted:true
}
```

## 7. Verifier (`TelnetVerifier`) behavior

A **second, independent** Telnet session (new invocation id, new socket, fresh
authentication, fresh `cat flag.txt`). Checks:
`distinct_invocation, new_session, new_authentication, fresh_flag_observation,
candidate_hash_matches, causal_binding_valid, no_replayed_execution` → all
`true` ⇒ `classification="supported"` ⇒ `UNVERIFIED → VERIFIED`.

## 8. Falsifier behavior

A third, distinct session runs the mission's negative-control command (`ls`)
via purpose `mode=negative-control`. Predicate: if the candidate appeared in the
negative-control output it would be a counter-example (REFUTED). It did not, so
the finding stayed **VERIFIED**. Transition authority remains the `FindingStore`.

## 9. Tests

- **Unit (`test_d12_telnet.py`): 24** — schema/blank-password, command allow-list
  & forbidden shells, exact target/port/protocol authorization, mission binding,
  DENY-without-execution, replay prevention, timeout/bounds, password-not-persisted,
  evidence hashing, candidate extraction, independent verification, falsification,
  probe evidence, auth-failure, and the normal `/operations/start` path.
- **Live (`test_d12_telnet_live.py`): 1** — skipped unless `RAPHAEL_LIVE_MEOW=1`
  (passes: run `20260922T193249_ff36fc`).

## 10. Regression count

**393 tests, 0 failures** (D7/D8/D9/D9.1/D9.2/D10.1/D10.2/D11 + M6/M2/seam/
harness/M13/M15.1–M15.6 + D12).

## 11. Live run

| Field | Value |
|---|---|
| Run ID | `20260922T193147_4e0196` |
| Target | `10.129.223.207:23` (Telnet) |
| Authentication | **accepted** (`auth_decision=accepted`, `authenticated=true`) |
| Flag extracted | **PRESENT** (`flag_sha256=a869860b…ffbe`) |
| Verification | **supported** (all independence checks true) → VERIFIED |
| Falsifier | negative-control `ls` observed; no counter-example |

Requests (order): `telnet-session` (flag) → `telnet-session` (verify) →
`telnet-session mode=negative-control` → `telnet-session mode=probe` →
`run_test`.

## 12. QualityGate A–G

```
[A] mission-criterion           PASS
[B] required-tests              PASS
[C] regression                  PASS
[D] independent-behavior-probe  PASS
[E] scope                       PASS
[F] evidence                    PASS
[G] finding-state               PASS   (Finding VERIFIED)
FINAL: COMPLETE (7/7)
```

## 13. Boundary

D1–D11 remain frozen. D12 adds exactly one capability
(`NETWORK_TELNET_SESSION`) for governed flag retrieval via an allow-listed
command set. It does not add SMB, SSH, arbitrary shell, privilege escalation,
lateral movement, scanning, or exploitation frameworks. Claim: **Raphael
governably solved Meow through Telnet** — and nothing more.

---

## 14. Correction — flag representation & provenance (revalidation)

The earlier report labelled `flag_sha256` as if it were the flag. It is a
digest. The implementation now distinguishes three things explicitly:

| Term | Meaning |
|---|---|
| `raw_flag` | the candidate exactly as it appeared in the `cat flag.txt` output |
| `flag_sha256` | SHA-256 of `raw_flag` (a digest — **not** the flag) |
| `submission_flag` | HTB submission representation `HTB{<raw_flag>}` |

**Extraction is now strict:** the mediator accepts only **exactly one**
token-bounded match of the mission pattern (`[0-9a-f]{32}`), sourced **only**
from the declared `flag_command` (`cat flag.txt`). Ambiguity (0 or >1 matches,
embedded-in-longer-hex, uppercase, wrong length) fails closed.

**Provenance proof (live, values never printed):**

```
cmd='pwd'           bytes=5   candidates=0
cmd='ls'            bytes=14  candidates=0
cmd='cat flag.txt'  bytes=32  candidates=1   <- exactly one 32-hex
```

**Revalidation result (run `20260922T194600_63aa87`):**

| Item | Result |
|---|---|
| Authentication | accepted (`authenticated=true`) |
| raw candidate | **PRESENT** (`candidate_count=1`, `candidate_valid=true`) |
| Format validation | 32 chars, lowercase, all-hex → valid |
| candidate_sha256 | `a869860b…ffbe` |
| `flag_source_command` | `cat flag.txt` |
| `flag_output_sha256` | `a869860b…ffbe` (the output IS the raw candidate) |
| HTB submission | **PRESENT** (`HTB{<raw>}`, sha256 `75fd47dd…fb23`) |
| Independent verification | **supported** — all checks true (incl. `candidate_format_valid`), distinct invocation/session/auth/observation, hash match |
| Falsifier | negative-control `ls` observed; no counter-example; finding stays VERIFIED |
| QualityGate | A✓ B✓ C✓ D✓ E✓ F✓ G✓ → **COMPLETE (7/7)** |

The candidate was **not** compared against any hardcoded public value; the
proof originates entirely from the live target. The stale-prompt read bug
(command output read from a stale buffer) was fixed with a fresh per-command
buffer, and the provenance above shows the candidate is produced only by
`cat flag.txt`.
