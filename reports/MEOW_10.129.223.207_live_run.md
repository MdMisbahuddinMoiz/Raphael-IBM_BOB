# RAPHAEL × IBM BOB — Live Run Report: `10.129.223.207` (HTB "Meow")

**Run ID:** `20260922T191001_f1e3af`
**Date:** 2026-09-22
**Server:** started with `raphael-bob` (`python3 -m raphael_ibm_bob.http`, `127.0.0.1:8787`)
**VPN:** `starting_points_us-starting-point-2-dhcp.ovpn` → `tun0 10.10.15.172` (connected)
**Mode:** `TESTING / HTB`
**TargetProfile:** `TP-62a444418fc4fd59` — locator `10.129.223.207`, port `80`, protocol `http`, scope `10.129.223.207`
**QualityGate:** **REFUSE (6/7)** — condition **D** failed

---

## 1. Executive summary

Raphael drove the governed network mission against `10.129.223.207` end to end:
Policy ALLOWed every declared request, the boundary was honoured, the evidence
ledger was written, and the QualityGate returned an honest **REFUSE**.

**No flags were captured. No flag was fabricated.**

The target refused the HTTP connection (`[Errno 111] Connection refused`) on
port 80. `10.129.223.207` is the HTB Starting Point box **Meow**, whose only
network service is **Telnet (TCP/23)** — it exposes **no HTTP service**. Raphael's
governed network capability is `NETWORK_HTTP_REQUEST` (**HTTP GET/HEAD only**);
there is no Telnet, shell, or exploitation capability (by design, and frozen).
Therefore Meow's flags are **not reachable through the governed HTTP path** and
were **not** obtained.

---

## 2. Target identification

| Property | Value |
|---|---|
| IP | `10.129.223.207` |
| HTB box | Meow (Starting Point, Very Easy, Linux) |
| Documented service | Telnet (`tcp/23`) |
| HTTP service | **none** |
| Governed attempt | `GET http://10.129.223.207:80/` → connection refused |

The connection-refused result also confirms the host is **up** (a down host would
time out); the port is simply closed.

---

## 3. Governed run evidence

Every step went through the existing boundary
`Runtime → Broker → Policy → NetworkMediator`. Nothing bypassed Policy and no
verdict was manufactured.

| # | Capability | Target | Policy | Result |
|---|---|---|---|---|
| 1 | `network_http_request` | `http://10.129.223.207:80/` | ALLOW | `refused` (`[Errno 111]`) |
| 6 | `network_http_request` | `http://10.129.223.207:80/index.html` | ALLOW | `refused` (`[Errno 111]`) |
| 11 | `run_test` | `test_ok.py` | ALLOW | success (`returncode 0`) |

Network observations (evidence, `producer="network"`):

```text
/            state=refused  status=None  bytes=0  error=[Errno 111] Connection refused  flag=null
/index.html  state=refused  status=None  bytes=0  error=[Errno 111] Connection refused  flag=null
```

Independent behavior probe (`producer="probe"`): **absent** — the probe is a
separate governed HTTP observation; it could not succeed because the service is
not HTTP, so no `allowed=true` probe record exists.

Regression (`producer="regression"`):

```json
{"kind":"regression","mission_id":"M-HTB-001","request_seq":11,"result":"passed","result_seq":14,"returncode":0,"source":"network-run:required-test","test":"test_ok.py"}
```

QualityGate (persisted, sole completion authority):

```text
[A] mission-criterion           PASS
[B] required-tests              PASS
[C] regression                  PASS
[D] independent-behavior-probe  FAIL   <- behavior_probe_ok=False (no probe proof supplied)
[E] scope                       PASS
[F] evidence                    PASS
[G] finding-state               PASS
FINAL: REFUSE (6/7)
```

Machine-readable bundle: [`reports/meow-10.129.223.207/`](meow-10.129.223.207/)
(`run.json`, `ledger.jsonl`, `gate.json`, `summary.json`, `transcript.txt`).

---

## 4. Root cause

- **Capability boundary.** The only network capability is
  `NETWORK_HTTP_REQUEST` (HTTP GET/HEAD). Meow speaks Telnet, not HTTP.
- **No exploitation.** Raphael does not log into services, run commands,
  transfer files, or escalate privileges. Capturing Meow's flag would require
  interactive Telnet login — explicitly out of scope for this release and
  prohibited by the D1–D11 freeze (no Telnet capability, no arbitrary shell, no
  privilege escalation).
- **Consequence.** Because no HTTP observation succeeded, the independent
  behavior probe could not produce `allowed=true`, so QualityGate condition **D**
  failed and the gate refused. This is the correct, honest behaviour: failure
  was **not** converted into COMPLETE.

---

## 5. Integrity statement

- No flag was invented, guessed, or copied from any other source.
- No QualityGate semantics were changed, no condition was weakened, and
  `behavior_probe_ok`/`regression_ok` were not set without evidence.
- The persisted ledger was not altered; the export is a read-only copy.
- This report does **not** claim that Raphael solved Meow or captured its flags.

---

## 6. Options to obtain flags with Raphael

1. **HTTP-flag-serving target (supported today).** Point Raphael at a target that
   returns the flag in an HTTP response body (the validated Breakout demo reaches
   `COMPLETE 7/7` this way). Meow is unsuitable because it serves no HTTP.
2. **Add a governed Telnet capability (POST-HACKATHON, not in this freeze).**
   Would require a new capability + Policy rules + mediator + evidence + gate
   handling, and is intentionally excluded from the frozen architecture.
3. **Out-of-governance manual access (not “using Raphael”).** Logging into Meow
   by hand with a Telnet client is outside Raphael's governed boundary and was
   not performed.

---

## 7. Current environment (left running)

```text
Server   : raphael-bob  (python3 -m raphael_ibm_bob.http) on 127.0.0.1:8787
VPN      : connected (tun0 10.10.15.172, starting_points_us-starting-point-2-dhcp.ovpn)
Mode     : TESTING / HTB
Target   : TP-62a444418fc4fd59 (10.129.223.207:80)
Last run : 20260922T191001_f1e3af  -> REFUSE (6/7), no flag
```
