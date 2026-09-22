"""raphael_ibm_bob.broker — BOB MVP Broker implementation.

The Broker is the MANDATORY mediation layer between any caller (Runtime,
Verifier, Falsifier, Replanner) and any capability. It:

    1. Assigns a dense sequence number to each request.
    2. Consults the Policy BEFORE invoking any capability.
    3. Persists a canonical RequestRecord to the EvidenceLedger (M3).
    4. Persists a canonical DecisionRecord (ALLOW or DENY) (M3).
    5. On DENY: persists a PolicyEvidenceReceipt and returns
       PolicyDecision without invoking any handler. (M3)
    6. On ALLOW: invokes the capability via `execute_capability`, persists
       a ResultRecord and an ExecutionEvidenceReceipt. (M3)
    7. Returns the PolicyDecision (and, on ALLOW, the ExecutionResult).

The Broker is the ONLY component that calls into `execute_capability`.
Runtime, Verifier, Falsifier, Replanner, QualityGate, Planner, Runner
must all go through the Broker.

Legacy reference (ADAPT, not reused as-is):
    src/orchestrator/brain/capability_broker.py:266 CapabilityBroker
        - 5-dim authorization, deny-by-default, ActionReceipt shape.
        - Rebound at M2 to: capability allow-list, workspace scope,
          mission-scope substring, capability-specific invariants.
    src/orchestrator/brain/evidence.py
        - frozen-dataclass + SHA-256 digest pattern; the BOB MVP uses the
          same digest discipline at the record level.

Remaining limitations at M3:
    - Audit log field is retained for back-compat with M2 tests; the
      authoritative provenance is now the EvidenceLedger.
    - No rate limiting (MVP does not require it).
    - No replay protection.
"""
from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from raphael_ibm_bob.contracts import (
    ActionRequest,
    Capability,
    Decision,
    EvidenceReceipt,
    ExecutionResult,
    Mission,
    PolicyDecision,
)
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.capabilities import execute_capability
from raphael_ibm_bob.workspace import Workspace
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, digest_id
from raphael_ibm_bob.c1a_replay import (
    C1AReplayError,
    C1AReplayGuard,
    new_lineage,
)
from raphael_ibm_bob.network_runtime import (
    PROVIDER_UNTRUSTED,
    get_network_mediator,
)
from raphael_ibm_bob.telnet_runtime import (
    build_telnet_spec,
    get_telnet_mediator,
)
from raphael_ibm_bob.target_profile import get_target_store


@dataclass(frozen=True)
class BrokerResult:
    """Bundled result of a Broker.submit call."""
    decision: PolicyDecision
    execution: Optional[ExecutionResult]  # set only when ALLOW
    capability_invoked: bool              # True iff execute_capability ran
    request_seq: int                      # durable ledger sequence
    decision_seq: int                     # durable ledger sequence
    result_seq: Optional[int]            # durable ledger sequence (None on DENY)
    evidence_ids: Tuple[str, ...]         # durable evidence identifiers


class BOBBroker:
    """Mandatory mediation layer. Always consults Policy before invoking a capability.

    If `ledger` is provided, every action persists a canonical record chain
    to the ledger. If `ledger` is None, the broker behaves as it did at M2
    (in-memory audit only).

    T1-4: `default_timeouts` maps capabilities to execution bounds in
    seconds (RUN_TEST defaults to 30.0 when absent). A per-request
    `ActionRequest.timeout_seconds` overrides the default. Timeouts are
    enforced at invocation; a timeout is recorded as an unsuccessful
    execution — never as success, never rewritten as DENY.
    """

    def __init__(
        self,
        policy: BOBPolicy,
        workspace: Workspace,
        ledger: Optional[EvidenceLedger] = None,
        default_timeouts: Optional[Dict[Capability, float]] = None,
        c1a_provider: Optional[Any] = None,
        c1a_authorization: Optional[Any] = None,
        c1a_replay_guard: Optional[Any] = None,
        network_mediator: Optional[Any] = None,
        target_store: Optional[Any] = None,
        telnet_mediator: Optional[Any] = None,
    ):
        self._policy = policy
        self._workspace = workspace
        self._ledger = ledger
        for cap, seconds in (default_timeouts or {}).items():
            if seconds is None or seconds <= 0:
                raise ValueError(
                    f"default timeout for {cap!r} must be positive, "
                    f"got {seconds!r}")
        self._default_timeouts: Dict[Capability, float] = dict(
            default_timeouts or {})
        # C1A out-of-process provider (defaults to the fail-closed adapter)
        # and the authorization-binding authority (one per broker).
        self._c1a_provider = c1a_provider
        self._c1a_authorization = c1a_authorization
        # Replay/lineage guard for the governed C1A path (one per broker).
        # It prevents a ProviderResult/result lineage from one execution
        # being replayed or grafted onto another.
        self._c1a_replay_guard = (
            c1a_replay_guard if c1a_replay_guard is not None
            else C1AReplayGuard())
        # D9: governed network boundary (mediator) + authorized target store.
        self._network_mediator = network_mediator
        self._target_store = target_store
        # D12: governed Telnet boundary (its own mediator; additive).
        self._telnet_mediator = telnet_mediator
        self._lock = threading.Lock()
        self._sequence = 0
        # Diagnostic counters for tests/audit. Retained from M2.
        self.submissions: int = 0
        self.allows: int = 0
        self.denies: int = 0
        self.capability_invocations: int = 0
        # In-memory audit log retained for back-compat with M2 tests.
        # The authoritative provenance is the ledger.
        self.audit: List[Dict[str, Any]] = []

    @property
    def ledger(self) -> Optional[EvidenceLedger]:
        return self._ledger

    def attach_ledger(self, ledger: EvidenceLedger) -> None:
        """Attach (or replace) the EvidenceLedger after construction."""
        with self._lock:
            self._ledger = ledger

    @property
    def c1a_authorization(self) -> Any:
        return self._c1a_authorization

    @property
    def c1a_provider(self) -> Any:
        return self._c1a_provider

    @property
    def c1a_replay_guard(self) -> C1AReplayGuard:
        return self._c1a_replay_guard

    @property
    def network_mediator(self) -> Any:
        """The governed network mediator (injected or process singleton)."""
        if self._network_mediator is not None:
            return self._network_mediator
        from raphael_ibm_bob.network_runtime import get_network_mediator
        return get_network_mediator()

    @property
    def telnet_mediator(self) -> Any:
        """The governed Telnet mediator (injected or process singleton)."""
        if self._telnet_mediator is not None:
            return self._telnet_mediator
        return get_telnet_mediator()

    # Broker.seam interface ----------------------------------------------------

    def submit(self, request: ActionRequest, mission: Mission) -> BrokerResult:
        if (request.timeout_seconds is not None
                and request.timeout_seconds <= 0):
            raise ValueError(
                "ActionRequest.timeout_seconds must be positive, got "
                f"{request.timeout_seconds!r}")
        # T1-4: resolve the execution bound before anything else so the
        # stamped request, the decision evidence, and the capability
        # invocation all observe the same value.
        effective_timeout = request.timeout_seconds
        if effective_timeout is None:
            effective_timeout = self._default_timeouts.get(
                request.capability)
        if (effective_timeout is None
                and request.capability == Capability.RUN_TEST):
            effective_timeout = 30.0
        with self._lock:
            self.submissions += 1
            self._sequence += 1
            # Stamp the request sequence in case the caller did not.
            stamped = ActionRequest(
                sequence=self._sequence,
                requester=request.requester,
                capability=request.capability,
                target=request.target,
                purpose=request.purpose,
                plan_id=request.plan_id,
                finding_id=request.finding_id,
                timeout_seconds=effective_timeout,
            )
        # Persist the RequestRecord first so subsequent records can link.
        # The ledger's sequence number is the canonical request_seq; the
        # in-broker counter is retained for back-compat with the M2 audit
        # counters but the ledger is the source of truth for ordering.
        if self._ledger is not None:
            request_seq = self._ledger.append_request(stamped)
        else:
            request_seq = self._sequence

        # Consult Policy. ALLOW/DENY both must be honoured.
        decision = self._policy.consult(stamped, mission)
        with self._lock:
            if decision.decision == Decision.ALLOW:
                self.allows += 1
            else:
                self.denies += 1
            self.audit.append({"stage": "decision", **decision.to_dict()})

        # Persist the DecisionRecord.
        decision_seq = self._sequence + 1 if False else None  # placeholder
        if self._ledger is not None:
            decision_seq = self._ledger.append_decision(request_seq, decision)
        else:
            decision_seq = 0

        # Persist a PolicyEvidenceReceipt for the decision itself (always).
        evidence_ids: List[str] = []
        if self._ledger is not None:
            ev_id = digest_id({
                "request_seq": request_seq,
                "decision_seq": decision_seq,
                "decision": decision.decision.value,
                "reason": decision.reason,
            }, prefix="P")
            payload = {
                "decision": decision.decision.value,
                "reason": decision.reason,
                "capability": decision.capability.value,
                "target": decision.target,
                "request_seq": request_seq,
                "decision_seq": decision_seq,
                "timeout_seconds": effective_timeout,
            }
            self._ledger.append_evidence(
                evidence_id=ev_id,
                producer="policy",
                request_seq=request_seq,
                decision_seq=decision_seq,
                result_seq=None,
                payload=payload,
            )
            evidence_ids.append(ev_id)

        # On DENY: NO capability invocation, no side effect.
        if decision.decision == Decision.DENY:
            return BrokerResult(
                decision=decision,
                execution=None,
                capability_invoked=False,
                request_seq=request_seq,
                decision_seq=decision_seq,
                result_seq=None,
                evidence_ids=tuple(evidence_ids),
            )

        # On ALLOW: invoke the capability. C1A is a distinct,
        # out-of-process path; every other capability uses the native
        # in-process dispatch. C1A is NEVER aliased to READ.
        if stamped.capability == Capability.C1A_STATIC_FILE_INSPECT:
            return self._execute_c1a(
                stamped=stamped,
                mission=mission,
                request_seq=request_seq,
                decision_seq=decision_seq,
                effective_timeout=effective_timeout,
                evidence_ids=evidence_ids,
                decision=decision,
            )

        # D9: the single governed network path (HTTP only). It never uses
        # execute_capability and never spawns a shell; the Broker remains
        # the sole invoker and the mediator is the only network-I/O boundary.
        if stamped.capability == Capability.NETWORK_HTTP_REQUEST:
            return self._execute_network(
                stamped=stamped,
                mission=mission,
                request_seq=request_seq,
                decision_seq=decision_seq,
                evidence_ids=evidence_ids,
                decision=decision,
            )

        # D12: the governed Telnet path (additive). Same discipline: no
        # execute_capability, no shell; the telnet mediator is the only
        # Telnet-I/O boundary.
        if stamped.capability == Capability.NETWORK_TELNET_SESSION:
            return self._execute_telnet(
                stamped=stamped,
                mission=mission,
                request_seq=request_seq,
                decision_seq=decision_seq,
                evidence_ids=evidence_ids,
                decision=decision,
            )

        # On ALLOW: invoke the capability. We stamp the ExecutionResult
        # with the same sequence number so the linkage is unambiguous.
        # A timeout payload is an unsuccessful execution: the decision
        # stays ALLOW (it was authorized and attempted).
        result_seq: Optional[int] = None
        try:
            payload = execute_capability(self._workspace, stamped)
            if isinstance(payload, dict) and payload.get("timeout") is True:
                execution = ExecutionResult(
                    sequence=stamped.sequence,
                    success=False,
                    output="timeout",
                    error=f"TimeoutExpired after "
                          f"{payload.get('timeout_seconds')}s",
                    evidence=payload,
                )
            else:
                execution = ExecutionResult(
                    sequence=stamped.sequence,
                    success=True,
                    output="ok",
                    error=None,
                    evidence=payload,
                )
        except Exception as exc:
            execution = ExecutionResult(
                sequence=stamped.sequence,
                success=False,
                output="",
                error=f"{type(exc).__name__}:{exc}",
                evidence={},
            )

        with self._lock:
            self.capability_invocations += 1
            self.audit.append(
                {"stage": "execution", **execution.to_dict()}
            )

        if self._ledger is not None:
            result_seq = self._ledger.append_result(
                request_seq=request_seq,
                decision_seq=decision_seq,
                result=execution,
            )
            exec_ev_id = digest_id({
                "request_seq": request_seq,
                "decision_seq": decision_seq,
                "result_seq": result_seq,
                "success": execution.success,
            }, prefix="X")
            exec_payload = {
                "success": execution.success,
                "output": execution.output,
                "error": execution.error,
                "evidence_keys": sorted(execution.evidence.keys()),
                "request_seq": request_seq,
                "decision_seq": decision_seq,
                "result_seq": result_seq,
            }
            self._ledger.append_evidence(
                evidence_id=exec_ev_id,
                producer="execution",
                request_seq=request_seq,
                decision_seq=decision_seq,
                result_seq=result_seq,
                payload=exec_payload,
            )
            evidence_ids.append(exec_ev_id)

        return BrokerResult(
            decision=decision,
            execution=execution,
            capability_invoked=True,
            request_seq=request_seq,
            decision_seq=decision_seq,
            result_seq=result_seq,
            evidence_ids=tuple(evidence_ids),
        )

    # C1A out-of-process path ------------------------------------------------

    def _execute_c1a(
        self,
        *,
        stamped: ActionRequest,
        mission: Mission,
        request_seq: int,
        decision_seq: int,
        effective_timeout: Optional[float],
        evidence_ids: List[str],
        decision: PolicyDecision,
    ) -> BrokerResult:
        """Execute the C1A capability through the governed provider boundary.

        This is the ONLY path for C1A execution. It creates an authorization
        binding from the ALLOW decision, validates scope, invokes the
        provider through ``invoke_governed`` (which fails closed), converts
        the ProviderResult into UNTRUSTED evidence, and persists the chain.
        """
        from dataclasses import replace as _replace

        from raphael_ibm_bob.adapters.t3mp3st_adapter import T3MP3STAdapter
        from raphael_ibm_bob.c1a_authorization import (
            C1AAuthorizationBinding,
            C1AAuthorizationError,
        )
        from raphael_ibm_bob.c1a_evidence import (
            PROVIDER_UNTRUSTED,
            provider_result_to_execution,
        )
        from raphael_ibm_bob.provider_runtime import (
            ScopeViolation,
            fixture_digest,
            invoke_governed,
        )

        run_id = (self._ledger.run_dir().name
                  if self._ledger is not None else "in-memory")
        auth = (self._c1a_authorization
                if self._c1a_authorization is not None
                else C1AAuthorizationBinding())
        provider = (self._c1a_provider
                    if self._c1a_provider is not None
                    else T3MP3STAdapter())
        guard = self._c1a_replay_guard
        mission_id = mission.mission_id

        def _failure(error: str, **extra: Any) -> ExecutionResult:
            evidence: Dict[str, Any] = {PROVIDER_UNTRUSTED: True}
            evidence.update(extra)
            return ExecutionResult(
                sequence=stamped.sequence, success=False, output="",
                error=error, evidence=evidence)

        try:
            binding = auth.create_binding(
                decision=decision,
                request=stamped,
                run_id=run_id,
                mission_id=mission_id,
                workspace_root=str(self._workspace.root),
                timeout_seconds=effective_timeout,
            )
        except C1AAuthorizationError as exc:
            return self._finalize_c1a_result(
                stamped=stamped, decision=decision,
                execution=_failure(
                    f"C1AAuthorizationError:{exc}",
                    authorization_failed=True),
                request_seq=request_seq, decision_seq=decision_seq,
                evidence_ids=evidence_ids, mission_id=mission_id)

        invocation_id = binding.handoff.invocation_id

        # 1. Verify the freshly created binding BEFORE any provider dispatch.
        #    A binding that cannot be re-verified (tampered, consumed, or
        #    foreign) must never reach the provider.
        if not auth.verify_binding(invocation_id, decision):
            auth.invalidate_binding(invocation_id)
            return self._finalize_c1a_result(
                stamped=stamped, decision=decision,
                execution=_failure(
                    "C1AAuthorizationError:binding verification failed "
                    "before provider dispatch", authorization_failed=True),
                request_seq=request_seq, decision_seq=decision_seq,
                evidence_ids=evidence_ids, mission_id=mission_id)

        # 2. Register the execution lineage BEFORE provider dispatch so a
        #    replayed or cross-run invocation cannot execute and a result
        #    from another execution cannot be grafted onto this one.
        fixture_sha256 = fixture_digest(binding.handoff.fixture_path)["sha256"]
        lineage = new_lineage(
            run_id=run_id,
            invocation_id=invocation_id,
            proof_session_id=binding.handoff.proof_session_id,
            sandbox_id=binding.sandbox_id,
            fixture_path=binding.handoff.fixture_path,
            fixture_sha256=fixture_sha256,
        )
        try:
            guard.register(lineage)
        except C1AReplayError as exc:
            auth.invalidate_binding(invocation_id)
            return self._finalize_c1a_result(
                stamped=stamped, decision=decision,
                execution=_failure(f"C1AReplayError:{exc}",
                                   replay_rejected=True),
                request_seq=request_seq, decision_seq=decision_seq,
                evidence_ids=evidence_ids, mission_id=mission_id,
                lineage_hash=lineage.lineage_hash)

        # validate_scope compares the request target against the canonical
        # fixture literal; use the binding's canonical target so a relative
        # request target can never be ambiguously interpreted.
        scoped_request = _replace(
            stamped, target=binding.handoff.fixture_path)

        try:
            provider_result = invoke_governed(
                provider, binding.handoff, scoped_request)
            execution = provider_result_to_execution(
                provider_result, sequence=stamped.sequence)
        except ScopeViolation as exc:
            execution = _failure(f"ScopeViolation:{exc}")
        except Exception as exc:  # noqa: BLE001 - fail closed
            execution = _failure(
                f"{type(exc).__name__}:{exc}",
                failure_type=type(exc).__name__)
        finally:
            # Single-use: the binding can never authorize a second call.
            auth.invalidate_binding(invocation_id)

        return self._finalize_c1a_result(
            stamped=stamped, decision=decision, execution=execution,
            request_seq=request_seq, decision_seq=decision_seq,
            evidence_ids=evidence_ids, mission_id=mission_id,
            lineage_hash=lineage.lineage_hash, fixture_sha256=fixture_sha256)

    def _finalize_c1a_result(
        self,
        *,
        stamped: ActionRequest,
        decision: PolicyDecision,
        execution: ExecutionResult,
        request_seq: int,
        decision_seq: int,
        evidence_ids: List[str],
        mission_id: str = "",
        lineage_hash: Optional[str] = None,
        fixture_sha256: Optional[str] = None,
    ) -> BrokerResult:
        """Persist a C1A result as provider (untrusted) evidence."""
        result_seq: Optional[int] = None

        with self._lock:
            self.capability_invocations += 1
            self.audit.append({"stage": "execution", **execution.to_dict()})

        if self._ledger is not None:
            result_seq = self._ledger.append_result(
                request_seq=request_seq,
                decision_seq=decision_seq,
                result=execution,
            )
            invocation_id = execution.evidence.get("invocation_id")
            exec_ev_id = digest_id({
                "request_seq": request_seq,
                "decision_seq": decision_seq,
                "result_seq": result_seq,
                "success": execution.success,
                "capability": "c1a_static_file_inspect",
                "invocation_id": invocation_id,
            }, prefix="X")
            exec_payload = {
                "success": execution.success,
                "output": execution.output,
                "error": execution.error,
                "capability": "c1a_static_file_inspect",
                "provider_untrusted": True,
                "invocation_id": invocation_id,
                "mission_id": mission_id,
                "lineage_hash": lineage_hash,
                "fixture_sha256": fixture_sha256,
                "evidence_keys": sorted(execution.evidence.keys()),
                "request_seq": request_seq,
                "decision_seq": decision_seq,
                "result_seq": result_seq,
            }
            self._ledger.append_evidence(
                evidence_id=exec_ev_id,
                producer="provider",
                request_seq=request_seq,
                decision_seq=decision_seq,
                result_seq=result_seq,
                payload=exec_payload,
            )
            evidence_ids.append(exec_ev_id)

        return BrokerResult(
            decision=decision,
            execution=execution,
            capability_invoked=True,
            request_seq=request_seq,
            decision_seq=decision_seq,
            result_seq=result_seq,
            evidence_ids=tuple(evidence_ids),
        )

    # D9 governed network path ------------------------------------------------

    def _execute_network(
        self,
        *,
        stamped: ActionRequest,
        mission: Mission,
        request_seq: int,
        decision_seq: int,
        evidence_ids: List[str],
        decision: PolicyDecision,
    ) -> BrokerResult:
        """Execute one governed HTTP request through the NetworkMediator.

        This is the ONLY path for the network capability. It creates a
        deterministic invocation bound to run/mission/target, delegates the
        single bounded HTTP request to the mediator (the only network-I/O
        boundary), and persists UNTRUSTED network evidence. It never calls
        execute_capability and never spawns a subprocess.
        """
        run_id = (self._ledger.run_dir().name
                  if self._ledger is not None else "in-memory")
        mediator = self._network_mediator or get_network_mediator()
        store = (self._target_store if self._target_store is not None
                 else get_target_store())
        profile = store.get_target(mission.mission_id)

        if profile is None:
            execution = ExecutionResult(
                sequence=stamped.sequence, success=False, output="",
                error="network-no-authorized-target",
                evidence={PROVIDER_UNTRUSTED: True})
        else:
            invocation_id = "NET-" + hashlib.sha256(
                f"{run_id}:{stamped.sequence}".encode("utf-8")
            ).hexdigest()[:16]
            result = mediator.invoke(
                request=stamped, profile=profile,
                invocation_id=invocation_id, run_id=run_id)
            data = result.to_dict()
            evidence: Dict[str, Any] = {
                "network_result": data,
                PROVIDER_UNTRUSTED: True,
                "capability": Capability.NETWORK_HTTP_REQUEST.value,
                "invocation_id": result.invocation_id,
                "mission_id": result.mission_id,
                "target_id": result.target_id,
                "flag": result.flag,
                "flag_sha256": result.flag_sha256,
                "response_sha256": result.response_sha256,
                "status_code": result.status_code,
                "truncated": result.truncated,
            }
            execution = ExecutionResult(
                sequence=stamped.sequence, success=result.success,
                output=(f"http:{result.status_code}"
                        if result.status_code is not None
                        else result.state.value),
                error=(result.error or None), evidence=evidence)

        with self._lock:
            self.capability_invocations += 1
            self.audit.append({"stage": "execution", **execution.to_dict()})

        result_seq: Optional[int] = None
        if self._ledger is not None:
            result_seq = self._ledger.append_result(
                request_seq=request_seq, decision_seq=decision_seq,
                result=execution)
            network_payload = dict(execution.evidence)
            network_payload.update({
                "request_seq": request_seq,
                "decision_seq": decision_seq,
                "result_seq": result_seq,
            })
            exec_ev_id = digest_id({
                "request_seq": request_seq,
                "decision_seq": decision_seq,
                "result_seq": result_seq,
                "invocation_id": execution.evidence.get("invocation_id"),
                "capability": Capability.NETWORK_HTTP_REQUEST.value,
            }, prefix="NX")
            self._ledger.append_evidence(
                evidence_id=exec_ev_id, producer="network",
                request_seq=request_seq, decision_seq=decision_seq,
                result_seq=result_seq, payload=network_payload)
            evidence_ids.append(exec_ev_id)

        return BrokerResult(
            decision=decision, execution=execution, capability_invoked=True,
            request_seq=request_seq, decision_seq=decision_seq,
            result_seq=result_seq, evidence_ids=tuple(evidence_ids))

    # D12 governed Telnet path ------------------------------------------------

    def _execute_telnet(
        self,
        *,
        stamped: ActionRequest,
        mission: Mission,
        request_seq: int,
        decision_seq: int,
        evidence_ids: List[str],
        decision: PolicyDecision,
    ) -> BrokerResult:
        """Execute one governed Telnet session through the TelnetMediator.

        The ONLY path for the Telnet capability. Builds the mission-declared
        session spec, delegates the single bounded session to the mediator
        (the only Telnet-I/O boundary), and persists UNTRUSTED telnet
        evidence. It never calls execute_capability and never spawns a shell.
        """
        run_id = (self._ledger.run_dir().name
                  if self._ledger is not None else "in-memory")
        mediator = self._telnet_mediator or get_telnet_mediator()
        store = (self._target_store if self._target_store is not None
                 else get_target_store())
        profile = store.get_target(mission.mission_id)

        if profile is None:
            execution = ExecutionResult(
                sequence=stamped.sequence, success=False, output="",
                error="telnet-no-authorized-target",
                evidence={PROVIDER_UNTRUSTED: True})
        else:
            spec = build_telnet_spec(mission, profile)
            if spec is None:
                execution = ExecutionResult(
                    sequence=stamped.sequence, success=False, output="",
                    error="telnet-no-session-spec",
                    evidence={PROVIDER_UNTRUSTED: True})
            else:
                invocation_id = "TEL-" + hashlib.sha256(
                    f"{run_id}:{stamped.sequence}".encode("utf-8")
                ).hexdigest()[:16]
                result = mediator.invoke(
                    request=stamped, profile=profile, spec=spec,
                    invocation_id=invocation_id, run_id=run_id)
                evidence: Dict[str, Any] = {
                    "telnet_result": result.to_dict(),
                    PROVIDER_UNTRUSTED: True,
                    "capability": Capability.NETWORK_TELNET_SESSION.value,
                    "invocation_id": result.invocation_id,
                    "mission_id": result.mission_id,
                    "target_id": result.target_id,
                    "authenticated": result.authenticated,
                    "auth_decision": result.auth_decision,
                    "flag": result.flag,
                    "flag_sha256": result.flag_sha256,
                    "session_bytes": result.session_bytes,
                }
                execution = ExecutionResult(
                    sequence=stamped.sequence, success=result.success,
                    output=f"telnet:{result.state.value}",
                    error=(result.error or None), evidence=evidence)

        with self._lock:
            self.capability_invocations += 1
            self.audit.append({"stage": "execution", **execution.to_dict()})

        result_seq: Optional[int] = None
        if self._ledger is not None:
            result_seq = self._ledger.append_result(
                request_seq=request_seq, decision_seq=decision_seq,
                result=execution)
            telnet_payload = dict(execution.evidence)
            telnet_payload.update({
                "request_seq": request_seq, "decision_seq": decision_seq,
                "result_seq": result_seq,
            })
            exec_ev_id = digest_id({
                "request_seq": request_seq, "decision_seq": decision_seq,
                "result_seq": result_seq,
                "invocation_id": execution.evidence.get("invocation_id"),
                "capability": Capability.NETWORK_TELNET_SESSION.value,
            }, prefix="TX")
            self._ledger.append_evidence(
                evidence_id=exec_ev_id, producer="telnet",
                request_seq=request_seq, decision_seq=decision_seq,
                result_seq=result_seq, payload=telnet_payload)
            evidence_ids.append(exec_ev_id)

        return BrokerResult(
            decision=decision, execution=execution, capability_invoked=True,
            request_seq=request_seq, decision_seq=decision_seq,
            result_seq=result_seq, evidence_ids=tuple(evidence_ids))

    def next_sequence(self) -> int:
        with self._lock:
            return self._sequence + 1

__all__ = ["BOBBroker", "BrokerResult"]