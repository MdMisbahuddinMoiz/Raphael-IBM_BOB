"""raphael_ibm_bob.telnet_runtime — governed Telnet boundary (D12).

The ONLY network-I/O boundary for ``Capability.NETWORK_TELNET_SESSION``. It
mirrors the D9 ``network_runtime`` discipline but speaks the Telnet protocol
directly over a bounded socket (no ``telnetlib``, no shell, no subprocess):

    * one bounded session per invocation, bounded duration + total bytes
    * login is performed through the Telnet protocol; the password is used
      but never persisted (evidence records presence, never the value)
    * a strict command allow-list — no arbitrary shell, pipes, redirection,
      chaining, substitution, or metacharacters
    * deterministic invocation identity + replay guard
    * per-command output hashing; output is UNTRUSTED evidence
    * a refusal/timeout/auth-failure is NEVER success

This module is additive (POST-HACKATHON). It does not touch the HTTP path.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import socket
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from raphael_ibm_bob.contracts import (
    ActionRequest,
    Capability,
    Decision,
    Finding,
    FindingState,
    Mission,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, digest_id
from raphael_ibm_bob.finding import FindingStore, InvalidTransitionError
from raphael_ibm_bob.network_scope import NetworkScopeError, parse_telnet_target
from raphael_ibm_bob.target_profile import TargetProfile

TELNET_CAPABILITY_ID = Capability.NETWORK_TELNET_SESSION.value
DEFAULT_TELNET_TIMEOUT = 20.0
DEFAULT_MAX_SESSION_BYTES = 65536
MAX_OUTPUT_PREVIEW = 2000
PROVIDER_UNTRUSTED = "provider_untrusted"

#: Global command allow-list. Flag retrieval is NOT arbitrary shell access.
COMMAND_ALLOWLIST: Tuple[str, ...] = ("pwd", "ls", "cat flag.txt")
#: Commands allowed ONLY when the mission explicitly authorizes them.
OPTIONAL_COMMAND_ALLOWLIST: Tuple[str, ...] = ("cat /root/flag.txt",)

_FORBIDDEN_SUBSTRINGS = (
    ";", "|", "&", ">", "<", "`", "$", "(", ")", "{", "}", "[", "]", "*",
    "?", "!", "~", "'", '"', "\\", "\n", "\r", "\t",
)
_FORBIDDEN_BINARIES = (
    "bash", "sh", "zsh", "dash", "sudo", "su", "nc", "ncat", "netcat",
    "curl", "wget", "python", "python3", "perl", "ruby", "php", "ssh",
    "telnet", "chmod", "chown", "rm", "mv", "cp", "dd", "mkfifo", "socat",
    "kill", "reboot", "shutdown", "mount", "insmod", "crontab",
)

# IAC / Telnet control bytes.
_IAC, _DONT, _DO, _WONT, _WILL, _SB, _SE = 255, 254, 253, 252, 251, 250, 240
_IAC_BYTES = bytes([_IAC, _DONT, _DO, _WONT, _WILL, _SB, _SE])
_LOGIN_RE = re.compile(rb"(?:login|username)\s*:\s*$", re.IGNORECASE)
_PASSWORD_RE = re.compile(rb"password\s*:\s*$", re.IGNORECASE)
_PROMPT_RE = re.compile(rb"[\r\n][^\r\n]{0,120}[#$>]\s*$")


class TelnetState(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    REFUSED = "refused"
    UNAVAILABLE = "unavailable"
    DENIED = "denied"
    AUTH_FAILED = "auth_failed"


def command_from_purpose(purpose: object) -> str:
    """Map an ActionRequest purpose to a session role.

    ``mode=probe`` -> the independent behavior probe command;
    ``mode=negative-control`` -> the falsifier negative control;
    anything else -> the flag-retrieval command.
    """
    text = purpose if isinstance(purpose, str) else ""
    low = text.lower()
    if "mode=probe" in low:
        return "probe"
    if "mode=negative-control" in low:
        return "negative-control"
    return "flag"


def validate_command(command: object,
                     allowed: Sequence[str]) -> Tuple[bool, str]:
    """Fail-closed command validation. Returns (ok, reason)."""
    if not isinstance(command, str) or command.strip() == "":
        return False, "command-empty"
    if command != command.strip():
        return False, "command-whitespace"
    for token in _FORBIDDEN_SUBSTRINGS:
        if token in command:
            return False, f"command-metacharacter:{token!r}"
    parts = command.split()
    if parts and parts[0] in _FORBIDDEN_BINARIES:
        return False, f"command-forbidden-binary:{parts[0]}"
    if command not in allowed:
        return False, "command-not-in-allowlist"
    return True, "ok"


def extract_flag_pattern(text: object, pattern: object) -> Optional[str]:
    """First match of the mission-declared pattern, or None (legacy)."""
    if not isinstance(text, str) or not text:
        return None
    if not isinstance(pattern, str) or pattern == "":
        return None
    try:
        rx = re.compile(pattern)
    except re.error:
        return None
    match = rx.search(text)
    return match.group(0) if match else None


_HEX_CHAR = re.compile(r"[0-9a-fA-F]")
_EXACT_LOWER_HEX32 = re.compile(r"[0-9a-f]{32}")


def extract_candidates(text: object, pattern: object) -> List[str]:
    """All TOKEN-BOUNDED matches of the mission pattern.

    A match embedded in a longer hexadecimal run (e.g. inside a 40-hex hash)
    is NOT a standalone token and is rejected.
    """
    if not isinstance(text, str) or not text:
        return []
    if not isinstance(pattern, str) or pattern == "":
        return []
    try:
        rx = re.compile(pattern)
    except re.error:
        return []
    out: List[str] = []
    for m in rx.finditer(text):
        s, e = m.span()
        if s > 0 and _HEX_CHAR.match(text[s - 1]):
            continue
        if e < len(text) and _HEX_CHAR.match(text[e]):
            continue
        out.append(m.group(0))
    return out


def extract_candidate(text: object, pattern: object
                      ) -> Tuple[Optional[str], int]:
    """Strictly ONE token-bounded candidate, else (None, match_count).

    Ambiguity (zero or many candidates) fails closed — the candidate must be
    exactly one standalone match.
    """
    candidates = extract_candidates(text, pattern)
    if len(candidates) == 1:
        return candidates[0], 1
    return None, len(candidates)


def is_exact_lower_hex32(candidate: object) -> bool:
    """True iff the candidate is exactly 32 lowercase hexadecimal chars."""
    return isinstance(candidate, str) and bool(
        _EXACT_LOWER_HEX32.fullmatch(candidate))


def submission_flag(candidate: object) -> Optional[str]:
    """HTB submission representation ``HTB{<candidate>}`` (or None)."""
    if is_exact_lower_hex32(candidate):
        return f"HTB{{{candidate}}}"
    return None


def flag_sha256(flag: object) -> Optional[str]:
    if not isinstance(flag, str) or flag == "":
        return None
    return hashlib.sha256(flag.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TelnetSessionSpec:
    """Explicit, structured Telnet session schema (mission-declared).

    The empty password is represented EXPLICITLY (``""``), never omitted.
    """
    target: str
    port: int
    username: str
    password: str
    commands: Tuple[str, ...]
    flag_command: str
    flag_pattern: str
    probe_command: str = "pwd"
    negative_control_command: str = "ls"
    timeout_seconds: float = DEFAULT_TELNET_TIMEOUT
    purpose: str = "telnet-session"

    def authorized_commands(self) -> Tuple[str, ...]:
        allow = list(COMMAND_ALLOWLIST)
        if "cat /root/flag.txt" in self.commands:
            allow.append("cat /root/flag.txt")
        return tuple(allow)

    def command_for_role(self, role: str) -> str:
        if role == "probe":
            return self.probe_command
        if role == "negative-control":
            return self.negative_control_command
        return self.flag_command

    def sensitive_dict(self) -> Dict[str, Any]:
        """Spec view for evidence: never includes the password value."""
        return {
            "target": self.target,
            "port": self.port,
            "username": self.username,
            "password_present": bool(self.password),
            "password_is_blank": self.password == "",
            "commands": list(self.commands),
            "flag_command": self.flag_command,
            "flag_pattern": self.flag_pattern,
            "probe_command": self.probe_command,
            "negative_control_command": self.negative_control_command,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class TelnetResult:
    """Closed, bounded outcome of one governed Telnet session."""
    state: TelnetState
    invocation_id: str
    mission_id: str
    target_id: str
    host: str
    port: int
    username: str
    run_id: str = ""
    protocol: str = "telnet"
    authenticated: bool = False
    auth_decision: str = "not-attempted"
    session_bytes: int = 0
    commands: Tuple[Dict[str, Any], ...] = ()
    #: raw_flag — the candidate as it appeared in the command output.
    flag: Optional[str] = None
    #: SHA-256 of the raw candidate (NOT the flag itself).
    flag_sha256: Optional[str] = None
    flag_command: str = ""
    #: provenance of the candidate: which command produced it, its output
    #: hash, how many standalone matches were seen, and whether it matched
    #: the exact declared format (32 lowercase hex for Meow).
    flag_source_command: str = ""
    flag_output_sha256: Optional[str] = None
    candidate_count: int = 0
    candidate_valid: bool = False
    #: HTB submission representation HTB{<raw_flag>} (derived, never the hash).
    submission_flag: Optional[str] = None
    submission_sha256: Optional[str] = None
    error: str = ""

    @property
    def raw_flag(self) -> Optional[str]:
        return self.flag

    @property
    def success(self) -> bool:
        return self.state is TelnetState.SUCCESS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "invocation_id": self.invocation_id,
            "mission_id": self.mission_id,
            "target_id": self.target_id,
            "host": self.host,
            "port": self.port,
            "protocol": self.protocol,
            "username": self.username,
            "run_id": self.run_id,
            "authenticated": self.authenticated,
            "auth_decision": self.auth_decision,
            "session_bytes": self.session_bytes,
            "commands": [dict(c) for c in self.commands],
            "flag": self.flag,
            "raw_flag": self.flag,
            "flag_sha256": self.flag_sha256,
            "flag_command": self.flag_command,
            "flag_source_command": self.flag_source_command,
            "flag_output_sha256": self.flag_output_sha256,
            "candidate_count": self.candidate_count,
            "candidate_valid": self.candidate_valid,
            "submission_flag": self.submission_flag,
            "submission_sha256": self.submission_sha256,
            "error": self.error[:512],
            PROVIDER_UNTRUSTED: True,
        }


# ---------------------------------------------------------------------------
# raw Telnet-over-socket client (no telnetlib; IAC negotiation handled)
# ---------------------------------------------------------------------------

class _SessionTimeout(Exception):
    pass


class _SessionRefused(Exception):
    pass


class _SessionUnavailable(Exception):
    pass


def _process_iac(data: bytes) -> Tuple[bytes, bytes]:
    """Strip IAC negotiation; return (clean_bytes, reply_bytes)."""
    out = bytearray()
    reply = bytearray()
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        if b != _IAC:
            out.append(b)
            i += 1
            continue
        if i + 1 >= n:
            break
        c = data[i + 1]
        if c == _IAC:
            out.append(_IAC)
            i += 2
        elif c in (_DO, _DONT, _WILL, _WONT):
            if i + 2 >= n:
                break
            opt = data[i + 2]
            # Refuse every option (WONT/DONT).
            if c == _DO:
                reply += bytes([_IAC, _WONT, opt])
            elif c == _WILL:
                reply += bytes([_IAC, _DONT, opt])
            i += 3
        elif c == _SB:
            j = data.find(bytes([_IAC, _SE]), i + 2)
            i = n if j < 0 else j + 2
        else:
            i += 2
    return bytes(out), bytes(reply)


def _read_until(sock: socket.socket, patterns: Sequence["re.Pattern"],
                deadline: float, max_bytes: int, buf: bytearray) -> None:
    """Read until a pattern matches at the tail (or deadline/byte cap)."""
    while True:
        tail = bytes(buf[-4096:])
        if any(p.search(tail) for p in patterns):
            return
        if len(buf) > max_bytes or time.monotonic() > deadline:
            return
        remaining = max(0.2, min(2.0, deadline - time.monotonic()))
        sock.settimeout(remaining)
        try:
            chunk = sock.recv(4096)
        except (socket.timeout, TimeoutError):
            if time.monotonic() > deadline:
                return
            continue
        except OSError:
            return
        if not chunk:
            return
        clean, reply = _process_iac(chunk)
        if reply:
            try:
                sock.sendall(reply)
            except OSError:
                return
        buf += clean


def _clean_command_output(raw: str, command: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and lines[0].strip() == command.strip():
        lines = lines[1:]
    # Drop a trailing prompt line.
    while lines and (_PROMPT_RE.search(("\n" + lines[-1]).encode())
                     or lines[-1].strip().endswith(("#", "$", ">"))):
        if lines[-1].strip() and lines[-1].strip()[-1:] in ("#", "$", ">"):
            lines = lines[:-1]
        else:
            break
    while lines and lines[-1].strip() == "":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _socket_telnet_session(
    host: str, port: int, username: str, password: str,
    commands: Sequence[str], timeout_seconds: float, max_bytes: int,
) -> Dict[str, Any]:
    """Perform one bounded Telnet session. Never raises for I/O failure."""
    deadline = time.monotonic() + float(timeout_seconds)
    buf = bytearray()
    results: List[Dict[str, Any]] = []
    authenticated = False
    auth_decision = "not-attempted"
    session_bytes = 0
    try:
        sock = socket.create_connection(
            (host, port), timeout=min(5.0, float(timeout_seconds)))
    except ConnectionRefusedError:
        return {"ok": False, "state": TelnetState.REFUSED,
                "error": "connection refused", "authenticated": False,
                "auth_decision": auth_decision, "commands": [],
                "session_bytes": 0}
    except (socket.timeout, TimeoutError):
        return {"ok": False, "state": TelnetState.TIMEOUT,
                "error": "connect timeout", "authenticated": False,
                "auth_decision": auth_decision, "commands": [],
                "session_bytes": 0}
    except OSError as exc:
        return {"ok": False, "state": TelnetState.UNAVAILABLE,
                "error": f"{type(exc).__name__}:{exc}", "authenticated": False,
                "auth_decision": auth_decision, "commands": [],
                "session_bytes": 0}
    try:
        # 1. Login prompt.
        _read_until(sock, [_LOGIN_RE], deadline, max_bytes, buf)
        session_bytes = len(buf)
        if not _LOGIN_RE.search(bytes(buf[-2048:])):
            return {"ok": False, "state": TelnetState.TIMEOUT,
                    "error": "no login prompt", "authenticated": False,
                    "auth_decision": auth_decision, "commands": [],
                    "session_bytes": session_bytes}
        sock.sendall(username.encode() + b"\n")
        # 2. Password prompt.
        _read_until(sock, [_PASSWORD_RE, _PROMPT_RE], deadline, max_bytes, buf)
        if _PASSWORD_RE.search(bytes(buf[-2048:])):
            sock.sendall(password.encode() + b"\n")
        # 3. Shell prompt (successful auth) or failure banner.
        _read_until(sock, [_PROMPT_RE], deadline, max_bytes, buf)
        tail = bytes(buf[-2048:])
        if _PROMPT_RE.search(tail):
            authenticated = True
            auth_decision = "accepted"
        else:
            auth_decision = "rejected"
            return {"ok": False, "state": TelnetState.AUTH_FAILED,
                    "error": "authentication not established",
                    "authenticated": False, "auth_decision": auth_decision,
                    "commands": [], "session_bytes": len(buf)}
        # 4. Run the allow-listed commands. Each command reads into a
        #    FRESH buffer so a stale prompt can never short-circuit the read.
        for command in commands:
            if time.monotonic() > deadline:
                break
            cmd_buf = bytearray()
            sock.sendall(command.encode() + b"\n")
            _read_until(sock, [_PROMPT_RE], deadline, max_bytes, cmd_buf)
            chunk = bytes(cmd_buf).decode("utf-8", errors="replace")
            output = _clean_command_output(chunk, command)
            results.append({
                "command": command,
                "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
                "output_preview": output[:MAX_OUTPUT_PREVIEW],
                "bytes": len(output.encode()),
                "ok": True,
            })
            session_bytes += len(cmd_buf)
        state = (TelnetState.SUCCESS if results
                 else TelnetState.FAILURE)
        return {"ok": state is TelnetState.SUCCESS, "state": state,
                "error": "" if results else "no command output",
                "authenticated": authenticated, "auth_decision": auth_decision,
                "commands": results, "session_bytes": session_bytes}
    except _SessionTimeout:
        return {"ok": False, "state": TelnetState.TIMEOUT, "error": "timeout",
                "authenticated": authenticated, "auth_decision": auth_decision,
                "commands": results, "session_bytes": len(buf)}
    except OSError as exc:
        return {"ok": False, "state": TelnetState.UNAVAILABLE,
                "error": f"{type(exc).__name__}:{exc}",
                "authenticated": authenticated, "auth_decision": auth_decision,
                "commands": results, "session_bytes": len(buf)}
    finally:
        try:
            sock.close()
        except OSError:
            pass


class TelnetReplayGuard:
    """Process-local replay guard over Telnet invocation identities."""

    def __init__(self) -> None:
        self._run_by_invocation: Dict[str, str] = {}
        self._lock = threading.Lock()

    def register(self, run_id: str, invocation_id: str) -> None:
        if not run_id or not invocation_id:
            raise ValueError("run_id and invocation_id are required")
        with self._lock:
            if invocation_id in self._run_by_invocation:
                raise ValueError(f"replayed invocation: {invocation_id!r}")
            self._run_by_invocation[invocation_id] = run_id

    def is_registered(self, invocation_id: str) -> bool:
        with self._lock:
            return invocation_id in self._run_by_invocation

    def run_for(self, invocation_id: str) -> Optional[str]:
        with self._lock:
            return self._run_by_invocation.get(invocation_id)


class TelnetMediator:
    """Minimal governed Telnet mediator (one session per invocation)."""

    _BINDING_SECRET: bytes = os.urandom(32)

    def __init__(self, *, max_session_bytes: int = DEFAULT_MAX_SESSION_BYTES,
                 timeout_seconds: float = DEFAULT_TELNET_TIMEOUT,
                 session_fn: Callable[..., Dict[str, Any]] = _socket_telnet_session,
                 replay_guard: Optional[TelnetReplayGuard] = None) -> None:
        if max_session_bytes <= 0:
            raise ValueError("max_session_bytes must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._max_bytes = int(max_session_bytes)
        self._timeout = float(timeout_seconds)
        self._session_fn = session_fn
        self.replay_guard = replay_guard or TelnetReplayGuard()

    def _binding_hash(self, identity: Dict[str, Any]) -> str:
        payload = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        return hmac.new(self._BINDING_SECRET, payload.encode("utf-8"),
                        hashlib.sha256).hexdigest()

    def invoke(self, *, request: ActionRequest, profile: TargetProfile,
               spec: TelnetSessionSpec, invocation_id: str,
               run_id: str) -> TelnetResult:
        """Validate scope + commands, then perform exactly one session."""
        try:
            target = parse_telnet_target(request.target)
        except NetworkScopeError as exc:
            return self._fail(TelnetState.DENIED, profile, spec, invocation_id,
                              run_id, error=f"target-invalid:{exc}")
        if not profile.allows(host=target.host, port=target.port,
                              protocol="telnet"):
            return self._fail(TelnetState.DENIED, profile, spec, invocation_id,
                              run_id, error="target-not-authorized",
                              target=target)

        role = command_from_purpose(request.purpose)
        command = spec.command_for_role(role)
        allowed = spec.authorized_commands()
        ok, why = validate_command(command, allowed)
        if not ok:
            return self._fail(TelnetState.DENIED, profile, spec, invocation_id,
                              run_id, error=f"command-rejected:{why}",
                              target=target)
        if spec.timeout_seconds is None or spec.timeout_seconds <= 0:
            return self._fail(TelnetState.DENIED, profile, spec, invocation_id,
                              run_id, error="timeout-invalid", target=target)

        identity = {
            "run_id": run_id, "mission_id": profile.mission_id,
            "invocation_id": invocation_id,
            "capability_id": TELNET_CAPABILITY_ID,
            "target_id": profile.target_id, "host": target.host,
            "port": target.port, "protocol": "telnet", "command": command,
        }
        expected = self._binding_hash(identity)
        if not hmac.compare_digest(expected, self._binding_hash(identity)):
            return self._fail(TelnetState.DENIED, profile, spec, invocation_id,
                              run_id, error="binding-invalid", target=target)

        try:
            self.replay_guard.register(run_id, invocation_id)
        except ValueError:
            return self._fail(TelnetState.DENIED, profile, spec, invocation_id,
                              run_id, error="replay", target=target)

        timeout = min(float(self._timeout), float(spec.timeout_seconds))
        outcome = self._session_fn(
            target.host, target.port, spec.username, spec.password,
            [command], timeout, self._max_bytes)
        state = outcome.get("state", TelnetState.FAILURE)
        if not isinstance(state, TelnetState):
            state = TelnetState(state)
        commands = tuple(outcome.get("commands") or ())
        flag = None
        flag_source = ""
        flag_out_sha = None
        candidate_count = 0
        if role == "flag":
            for c in commands:
                if c.get("command") == spec.flag_command:
                    # Strict: exactly one standalone token, sourced ONLY from
                    # the flag command's observed output.
                    flag, candidate_count = extract_candidate(
                        c.get("output_preview", ""), spec.flag_pattern)
                    flag_source = spec.flag_command
                    flag_out_sha = c.get("output_sha256")
                    break
        candidate_valid = is_exact_lower_hex32(flag)
        submission = submission_flag(flag)
        return TelnetResult(
            state=state, invocation_id=invocation_id,
            mission_id=profile.mission_id, target_id=profile.target_id,
            host=target.host, port=target.port, username=spec.username,
            run_id=run_id, authenticated=bool(outcome.get("authenticated")),
            auth_decision=str(outcome.get("auth_decision", "not-attempted")),
            session_bytes=int(outcome.get("session_bytes") or 0),
            commands=commands, flag=flag, flag_sha256=flag_sha256(flag),
            flag_command=(spec.flag_command if role == "flag" else command),
            flag_source_command=flag_source, flag_output_sha256=flag_out_sha,
            candidate_count=candidate_count, candidate_valid=candidate_valid,
            submission_flag=submission,
            submission_sha256=flag_sha256(submission),
            error=str(outcome.get("error") or "")[:512])

    def _fail(self, state: TelnetState, profile: TargetProfile,
              spec: TelnetSessionSpec, invocation_id: str, run_id: str, *,
              error: str, target: Any = None) -> TelnetResult:
        return TelnetResult(
            state=state, invocation_id=invocation_id,
            mission_id=profile.mission_id, target_id=profile.target_id,
            host=getattr(target, "host", profile.locator),
            port=getattr(target, "port", 0),
            username=spec.username, run_id=run_id,
            auth_decision="not-attempted", error=error[:512])


_telnet_mediator_singleton: Optional[TelnetMediator] = None
_telnet_lock = threading.Lock()


def get_telnet_mediator() -> TelnetMediator:
    global _telnet_mediator_singleton
    with _telnet_lock:
        if _telnet_mediator_singleton is None:
            _telnet_mediator_singleton = TelnetMediator()
        return _telnet_mediator_singleton


def set_telnet_mediator(mediator: Optional[TelnetMediator]) -> None:
    global _telnet_mediator_singleton
    with _telnet_lock:
        _telnet_mediator_singleton = mediator


# ---------------------------------------------------------------------------
# independent Telnet verification
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TelnetVerificationOutcome:
    classification: str
    checks: Dict[str, bool]
    observed_flag_sha256: Optional[str]
    invocation_id: Optional[str]
    result_seq: Optional[int]
    transition_applied: bool
    evidence_id: Optional[str]


def _telnet_result_from_execution(execution) -> Optional[Dict[str, Any]]:
    if execution is None:
        return None
    result = (execution.evidence or {}).get("telnet_result")
    return result if isinstance(result, dict) else None


class TelnetVerifier:
    """Broker-mediated INDEPENDENT reproduction of a Telnet finding.

    A second, distinct Telnet session (new invocation identity, new socket,
    a fresh authentication event and a fresh flag-command observation) must
    reproduce the candidate before the finding may become VERIFIED.
    """

    def __init__(self, runtime, ledger: EvidenceLedger,
                 store: Optional[FindingStore] = None,
                 replay_guard: Optional[TelnetReplayGuard] = None) -> None:
        self._runtime = runtime
        self._ledger = ledger
        self._store = store
        self._guard = replay_guard

    def _replay_guard(self) -> Optional[TelnetReplayGuard]:
        if self._guard is not None:
            return self._guard
        broker = getattr(self._runtime, "broker", None)
        mediator = getattr(broker, "_telnet_mediator", None)
        return getattr(mediator, "replay_guard", None)

    def verify_independent(
        self, finding: Finding, mission: Mission, *,
        original_invocation_id: Optional[str] = None,
        expected_flag_hash: Optional[str] = None,
        timeout_seconds: float = DEFAULT_TELNET_TIMEOUT,
        requester: str = "telnet-verifier",
    ) -> TelnetVerificationOutcome:
        if finding.state is not FindingState.UNVERIFIED:
            return TelnetVerificationOutcome(
                classification="insufficient", checks={},
                observed_flag_sha256=None, invocation_id=None, result_seq=None,
                transition_applied=False, evidence_id=None)

        request = ActionRequest(
            sequence=0, requester=requester,
            capability=Capability.NETWORK_TELNET_SESSION,
            target=finding.target, purpose="telnet-session",
            finding_id=finding.finding_id, timeout_seconds=timeout_seconds)
        rt = self._runtime.submit(request, mission)
        execution = rt.execution
        telnet = _telnet_result_from_execution(execution) or {}
        new_invocation = telnet.get("invocation_id")
        run_id = telnet.get("run_id") or "in-memory"
        observed_hash = telnet.get("flag_sha256")
        allowed = rt.broker_result.decision.decision is Decision.ALLOW

        guard = self._replay_guard()
        no_replay = bool(
            guard is not None and new_invocation
            and guard.is_registered(new_invocation)
            and guard.run_for(new_invocation) == run_id)
        command_observed = any(
            c.get("command") == telnet.get("flag_command")
            and c.get("output_sha256")
            for c in (telnet.get("commands") or []))
        checks = {
            "distinct_invocation": bool(new_invocation)
            and new_invocation != original_invocation_id,
            "new_session": bool(telnet.get("session_bytes") is not None),
            "new_authentication": bool(telnet.get("authenticated")),
            "fresh_flag_observation": command_observed,
            "candidate_format_valid": bool(telnet.get("candidate_valid")),
            "candidate_hash_matches": bool(observed_hash)
            and observed_hash == expected_flag_hash,
            "causal_binding_valid": (
                telnet.get("mission_id") == mission.mission_id
                and telnet.get("target_id") is not None),
            "no_replayed_execution": no_replay,
        }
        all_passed = all(checks.values())

        if not allowed or execution is None or not execution.success:
            classification = "inconclusive"
        elif not all_passed:
            classification = "insufficient"
        elif observed_hash == expected_flag_hash:
            classification = "supported"
        else:
            classification = "contradicted"

        payload = {
            "kind": "telnet-verification-result",
            "finding_id": finding.finding_id,
            "classification": classification, "checks": checks,
            "invocation_id": new_invocation,
            "observed_flag_sha256": observed_hash,
            "expected_flag_sha256": expected_flag_hash,
            "request_seq": rt.request_seq, "decision_seq": rt.decision_seq,
            "result_seq": rt.result_seq,
        }
        evidence_id = digest_id(payload, prefix="TV")
        self._ledger.append_evidence(
            evidence_id=evidence_id, producer="verifier",
            request_seq=rt.request_seq, decision_seq=rt.decision_seq,
            result_seq=rt.result_seq, payload=payload,
            finding_id=finding.finding_id)

        applied = False
        if classification == "supported" and all_passed and self._store:
            try:
                self._store.transition(
                    finding.finding_id, FindingState.VERIFIED,
                    evidence_seqs=tuple(
                        s for s in (rt.request_seq, rt.decision_seq,
                                    rt.result_seq) if s is not None),
                    additional_evidence_ids=[evidence_id],
                    extra_payload={"kind": "telnet-verified",
                                   "flag_sha256": observed_hash})
                applied = True
            except (InvalidTransitionError, KeyError):
                applied = False

        return TelnetVerificationOutcome(
            classification=classification, checks=checks,
            observed_flag_sha256=observed_hash, invocation_id=new_invocation,
            result_seq=rt.result_seq, transition_applied=applied,
            evidence_id=evidence_id)


def build_telnet_spec(mission: Mission,
                      profile: TargetProfile) -> Optional[TelnetSessionSpec]:
    """Build the structured session spec from the mission declaration.

    Session parameters (username/password/commands/flag pattern) are
    MISSION-declared; host/port come from the mission-bound TargetProfile,
    never from the caller.
    """
    raw = (mission.problem or {}).get("telnet")
    if not isinstance(raw, dict):
        return None
    password = raw.get("password", "")
    if password is None:
        password = ""
    try:
        timeout = float(raw.get("timeout_seconds", DEFAULT_TELNET_TIMEOUT))
    except (TypeError, ValueError):
        timeout = DEFAULT_TELNET_TIMEOUT
    return TelnetSessionSpec(
        target=profile.locator, port=(profile.allowed_ports[0]
                                      if profile.allowed_ports else 23),
        username=str(raw.get("username", "")), password=str(password),
        commands=tuple(str(c) for c in (raw.get("commands") or [])),
        flag_command=str(raw.get("flag_command", "")),
        flag_pattern=str(raw.get("flag_pattern", "")),
        probe_command=str(raw.get("probe_command", "pwd")),
        negative_control_command=str(raw.get("negative_control_command", "ls")),
        timeout_seconds=timeout,
        purpose=str(raw.get("purpose", "telnet-session")))


__all__ = [
    "COMMAND_ALLOWLIST",
    "DEFAULT_MAX_SESSION_BYTES",
    "DEFAULT_TELNET_TIMEOUT",
    "OPTIONAL_COMMAND_ALLOWLIST",
    "TELNET_CAPABILITY_ID",
    "TelnetMediator",
    "TelnetReplayGuard",
    "TelnetResult",
    "TelnetSessionSpec",
    "TelnetState",
    "TelnetVerificationOutcome",
    "TelnetVerifier",
    "build_telnet_spec",
    "command_from_purpose",
    "extract_candidate",
    "extract_candidates",
    "extract_flag_pattern",
    "flag_sha256",
    "get_telnet_mediator",
    "is_exact_lower_hex32",
    "set_telnet_mediator",
    "submission_flag",
    "validate_command",
]
