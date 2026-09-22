# RAPHAEL × IBM BOB — Live Demo Checklist

Operator checklist for the hackathon demo. Tick each item in order.
Server command (if not already running):

```bash
RAPHAEL_OPENVPN_BIN=/usr/sbin/openvpn PYTHONPATH=. \
  python3 -m raphael_ibm_bob.http --host 127.0.0.1 --port 8787
```

## Preflight

- [ ] Server started (pid recorded; log at `/tmp/raphael-http.log`)
- [ ] `./scripts/run_hackathon_demo.sh --preflight` reports **READY**

## UI walkthrough

- [ ] `/command` opens (Command Center)
- [ ] `/operations` opens
- [ ] **TESTING** selected
- [ ] **HTB** selected
- [ ] `GET /vpn/status` shows connected (only required for external HTB targets)
- [ ] TargetProfile configured (`POST /htb/target`; `GET /htb/target` shows it)
- [ ] Mission present (session created with the network mission)
- [ ] **Start operation** via `POST /operations/start`

## Success run (DEMO A)

- [ ] Network action visible (`NETWORK_HTTP_REQUEST`, primary observation)
- [ ] Policy **ALLOW** visible for the network request
- [ ] Network evidence visible (producer `network`, status/bytes)
- [ ] Independent probe visible (producer `probe`, `allowed=true`,
      invariant `authorized-http-endpoint-reachable-and-serving`)
- [ ] `RUN_TEST` visible (`test_ok.py`, `returncode=0`)
- [ ] Regression evidence visible (producer `regression`)
- [ ] Gate **A–G** visible on `/operations/{run_id}/decision-trace`
- [ ] **7/7 COMPLETE** visible (matches persisted gate record)
- [ ] Failed conditions show failed state; UNKNOWN stays UNKNOWN

## Refusal run (DEMO B)

- [ ] Refusal run available (`run_id` from `--refuse`, or an existing refused run)
- [ ] Gate shows **REFUSE** with **D** as the failed condition
- [ ] No "flag captured" / "solved" language anywhere

## Packaging

- [ ] `demo/success/` and `demo/refusal/` bundles present and consistent
- [ ] `./scripts/run_hackathon_demo.sh --tests` passes (0 failures)
