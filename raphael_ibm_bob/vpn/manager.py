"""raphael_ibm_bob.vpn.manager — controlled OpenVPN lifecycle.

The operator supplies an authorized ``.ovpn`` profile through the existing
BOB operator UI; this module owns the single active OpenVPN process:
start it with an argument array (never a shell), watch bounded stdout for
the tunnel handshake, expose a safe status view, and terminate it
deterministically.

Scope (hackathon MVP): one active VPN connection per server process,
associated with the active operator environment. BOB has no per-user
session context, so a single connection is the intended model. This is
NOT a general-purpose VPN manager.

Security posture
----------------
- subprocess execution uses an argument array; no shell is ever spawned.
- the OpenVPN executable is fixed by configuration / environment, never
  by request input.
- the profile is validated as data (:mod:`raphael_ibm_bob.vpn.profile`)
  and written to a private temp directory with mode ``0o600``.
- status never returns profile contents, credentials, or raw logs.

Honest limitations (documented, not hidden)
-------------------------------------------
- A crash of the whole server process can orphan a child OpenVPN; on the
  next start the manager makes a best-effort attempt to reap a process it
  previously recorded (PID + profile dir verified via ``/proc``) and then
  clears the record. If the host cannot verify the process identity, it
  is left alone and the limitation is logged.
- Interface / address detection is best-effort: it reads OpenVPN's own
  output and, when available, ``ip -o -4 addr``. No interface name or
  subnet is assumed.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

from raphael_ibm_bob.vpn.profile import ProfileError, validate_profile

logger = logging.getLogger("raphael_ibm_bob.vpn")

#: Environment override for the OpenVPN executable. Never request input.
OPENVPN_BIN_ENV = "RAPHAEL_OPENVPN_BIN"
DEFAULT_OPENVPN_BIN = "openvpn"

#: Default state root for profile material + the stale-process record.
DEFAULT_STATE_ROOT = Path(tempfile.gettempdir()) / "raphael-ibm-bob-vpn"

DEFAULT_CONNECT_TIMEOUT = 30.0
DEFAULT_DISCONNECT_TIMEOUT = 10.0
DEFAULT_MONITOR_POLL = 0.05
MAX_LOG_LINES = 200
MAX_EVENTS = 50

_INIT_RE = re.compile(r"Initialization Sequence Completed")
_IFACE_RES = (
    re.compile(r"TUN/TAP device (\S+) opened"),
    re.compile(r"Using TUN/TAP device (\S+)"),
)
_IP_RES = (
    re.compile(r"ip addr add dev (\S+) local (\d+\.\d+\.\d+\.\d+)"),
    re.compile(r"ifconfig\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)"),
)
_IP_ADDR_RES = re.compile(r"inet\s+(\d+\.\d+\.\d+\.\d+)")


class VPNError(Exception):
    """Base VPN failure with a stable code + HTTP status."""

    code = "VPN_ERROR"
    status = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class VPNProfileError(VPNError):
    code = "VPN_PROFILE_INVALID"
    status = 422


class VPNConflict(VPNError):
    code = "VPN_CONFLICT"
    status = 409


class VPNExecutableNotFound(VPNError):
    code = "VPN_EXECUTABLE_MISSING"
    status = 503


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _signal_group(proc: Any, sig: int) -> None:
    """Signal the process group when possible, else the process."""
    pid = getattr(proc, "pid", None)
    if pid:
        try:
            os.killpg(os.getpgid(pid), sig)
            return
        except (AttributeError, OSError):
            pass
    try:
        if sig == signal.SIGKILL:
            proc.kill()
        else:
            proc.terminate()
    except Exception:
        pass


def _pid_is_openvpn(pid: int, profile_dir: str) -> bool:
    """Best-effort identity check via /proc (Linux only)."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return False
    argv = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
    if not argv:
        return False
    if "openvpn" not in os.path.basename(argv[0]).lower():
        return False
    return profile_dir in " ".join(argv)


class VPNManager:
    """Owns the single active OpenVPN process and its lifecycle."""

    def __init__(
        self,
        *,
        openvpn_bin: Optional[str] = None,
        state_dir: Optional[Path] = None,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        disconnect_timeout: float = DEFAULT_DISCONNECT_TIMEOUT,
        monitor_poll: float = DEFAULT_MONITOR_POLL,
        which: Callable[[str], Optional[str]] = shutil.which,
        popen: Callable[..., Any] = subprocess.Popen,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._configured_bin = openvpn_bin
        self._state_dir = Path(state_dir) if state_dir else DEFAULT_STATE_ROOT
        self._connect_timeout = connect_timeout
        self._disconnect_timeout = disconnect_timeout
        self._monitor_poll = monitor_poll
        self._which = which
        self._popen = popen
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.RLock()

        self._state = "disconnected"
        self._state_since = _utcnow()
        self._profile_name: Optional[str] = None
        self._profile_dir: Optional[Path] = None
        self._proc: Any = None
        self._monitor: Optional[threading.Thread] = None
        self._init_seen = False
        self._interface: Optional[str] = None
        self._address: Optional[str] = None
        self._connected_at: Optional[str] = None
        self._error: Optional[str] = None
        self._stopping = False
        self._log: Deque[str] = deque(maxlen=MAX_LOG_LINES)
        self._events: Deque[Dict[str, str]] = deque(maxlen=MAX_EVENTS)

        self._reap_stale()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Return a safe, secret-free status view."""
        with self._lock:
            self._refresh_process_state()
            return {
                "state": self._state,
                "state_since": self._state_since,
                "profile_name": self._profile_name,
                "interface": self._interface,
                "address": self._address,
                "connected_at": self._connected_at,
                "process_state": self._process_state(),
                "pid": getattr(self._proc, "pid", None) if self._proc else None,
                "error": self._error,
                "history": list(self._events),
            }

    def connect(self, profile_text: object,
                profile_name: str = "profile.ovpn") -> Dict[str, Any]:
        """Validate a profile and start OpenVPN; wait for the tunnel.

        Pre-flight failures (bad profile, duplicate connect, missing
        executable) raise :class:`VPNError`. A runtime failure (timeout or
        early exit) is a legitimate lifecycle outcome: the manager ends in
        ``failed`` and returns the status, which the UI renders as FAILED.
        """
        with self._lock:
            if self._state in ("connecting", "connected", "disconnecting"):
                raise VPNConflict(
                    f"a VPN session is already {self._state}")
            try:
                validated = validate_profile(profile_text)
            except ProfileError as exc:
                self._set_state("failed", error=str(exc))
                raise VPNProfileError(str(exc)) from None

            binary = self._resolve_binary()
            self._record("VPN_CONNECT_REQUESTED")
            self._error = None
            self._profile_name = self._safe_name(profile_name)
            self._profile_dir = self._make_profile_dir(validated)
            self._init_seen = False
            self._interface = None
            self._address = None
            self._connected_at = None
            self._log.clear()
            self._stopping = False
            self._set_state("connecting")

            try:
                self._spawn(binary, self._profile_dir / "profile.ovpn")
            except OSError as exc:
                self._cleanup_profile_dir()
                self._set_state("failed",
                                error=f"failed to start openvpn: {exc}")
                raise VPNExecutableNotFound(
                    "failed to start the OpenVPN process") from None

            self._record("VPN_CONNECTING")
        # Release the lock while the monitor thread reads OpenVPN output;
        # `_await_connection` re-acquires it per inspection.
        return self._await_connection()

    def disconnect(self) -> Dict[str, Any]:
        """Terminate the VPN process and clean up; idempotent."""
        with self._lock:
            if self._proc is None and self._state == "disconnected":
                return self.status()
            self._record("VPN_DISCONNECT_REQUESTED")
            self._stopping = True
            self._set_state("disconnecting")
            self._terminate()
            self._set_state("disconnected", error=None)
            self._record("VPN_DISCONNECTED")
            return self.status()

    def shutdown(self) -> None:
        """Best-effort cleanup for interpreter exit."""
        try:
            with self._lock:
                if self._proc is not None:
                    self._stopping = True
                    self._terminate()
                    self._set_state("disconnected", error=None)
        except Exception:  # never raise during shutdown
            logger.exception("vpn shutdown failed")

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _resolve_binary(self) -> str:
        name = (self._configured_bin
                or os.environ.get(OPENVPN_BIN_ENV)
                or DEFAULT_OPENVPN_BIN)
        resolved = self._which(name)
        if not resolved:
            self._set_state(
                "failed",
                error=f"OpenVPN executable not found: {name}")
            raise VPNExecutableNotFound(
                f"OpenVPN executable not found: {name}")
        return resolved

    @staticmethod
    def _safe_name(name: object) -> str:
        text = str(name or "profile.ovpn")
        text = os.path.basename(text).strip() or "profile.ovpn"
        return text[:120]

    def _make_profile_dir(self, text: str) -> Path:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        profile_dir = Path(tempfile.mkdtemp(
            prefix="profile-", dir=str(self._state_dir)))
        path = profile_dir / "profile.ovpn"
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        return profile_dir

    def _cleanup_profile_dir(self) -> None:
        if self._profile_dir is not None:
            shutil.rmtree(self._profile_dir, ignore_errors=True)
            self._profile_dir = None

    def _spawn(self, binary: str, profile_path: Path) -> None:
        # Argument array only. The executable and profile path are fixed by
        # configuration, never by request input. No shell is involved.
        args = [binary, "--config", str(profile_path)]
        self._proc = self._popen(
            args,
            cwd=str(self._profile_dir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        self._write_marker()
        self._monitor = threading.Thread(
            target=self._monitor_output, name="vpn-monitor", daemon=True)
        self._monitor.start()

    def _monitor_output(self) -> None:
        stream = getattr(self._proc, "stdout", None)
        if stream is None:
            return
        try:
            for raw in stream:
                line = raw.rstrip("\n")
                if not line:
                    continue
                self._consume_line(line)
        except Exception:
            pass

    def _consume_line(self, line: str) -> None:
        with self._lock:
            self._log.append(line)
            if not self._init_seen and _INIT_RE.search(line):
                self._init_seen = True
            for rx in _IFACE_RES:
                match = rx.search(line)
                if match:
                    self._interface = match.group(1)
                    break
            for rx in _IP_RES:
                match = rx.search(line)
                if match:
                    groups = match.groups()
                    if groups[0].startswith("tun") or groups[0].startswith("tap"):
                        self._interface, self._address = groups[0], groups[1]
                    else:
                        # `ifconfig <local> <peer>`: local is the first group.
                        self._address = groups[0]
                    break

    def _await_connection(self) -> Dict[str, Any]:
        deadline = self._clock() + self._connect_timeout
        while self._clock() < deadline:
            with self._lock:
                proc = self._proc
                if proc is not None and proc.poll() is not None:
                    code = proc.returncode
                    self._terminate()
                    self._set_state(
                        "failed",
                        error="openvpn exited before the tunnel was "
                              f"established (exit code {code})")
                    self._record("VPN_CONNECTION_FAILED")
                    return self.status()
                if self._init_seen:
                    self._probe_address()
                    self._connected_at = _utcnow()
                    self._set_state("connected")
                    self._record("VPN_CONNECTED")
                    return self.status()
            self._sleep(self._monitor_poll)

        with self._lock:
            self._terminate()
            self._set_state(
                "failed",
                error=f"connection timed out after {self._connect_timeout:g}s")
            self._record("VPN_CONNECTION_FAILED")
            return self.status()

    def _probe_address(self) -> None:
        """Best-effort address lookup; never assumes an interface name."""
        if self._address or not self._interface:
            return
        ip_bin = self._which("ip")
        if not ip_bin:
            return
        try:
            result = subprocess.run(
                [ip_bin, "-o", "-4", "addr", "show", "dev", self._interface],
                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                timeout=3)
        except Exception:
            return
        match = _IP_ADDR_RES.search(result.stdout or "")
        if match:
            self._address = match.group(1)

    def _terminate(self) -> None:
        proc = self._proc
        if proc is not None:
            _signal_group(proc, signal.SIGTERM)
            if not self._wait_for_exit(proc, self._disconnect_timeout):
                _signal_group(proc, signal.SIGKILL)
                self._wait_for_exit(proc, 2.0)
        monitor = self._monitor
        if monitor is not None:
            monitor.join(timeout=2.0)
        self._proc = None
        self._monitor = None
        self._clear_marker()
        self._cleanup_profile_dir()

    def _wait_for_exit(self, proc: Any, timeout: float) -> bool:
        deadline = self._clock() + timeout
        while self._clock() < deadline:
            try:
                if proc.poll() is not None:
                    return True
            except Exception:
                return True
            self._sleep(self._monitor_poll)
        try:
            return proc.poll() is not None
        except Exception:
            return True

    def _refresh_process_state(self) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            code = proc.poll()
        except Exception:
            return
        if code is None:
            return
        if self._state in ("connecting", "connected") and not self._stopping:
            self._set_state(
                "failed",
                error=f"openvpn process exited unexpectedly (exit code {code})")
            self._record("VPN_PROCESS_EXITED")
            self._cleanup_profile_dir()
            self._clear_marker()

    def _process_state(self) -> str:
        proc = self._proc
        if proc is None:
            return "absent"
        try:
            return "running" if proc.poll() is None else "exited"
        except Exception:
            return "unknown"

    def _set_state(self, state: str, error: Optional[str] = None) -> None:
        self._state = state
        self._state_since = _utcnow()
        self._error = error

    def _record(self, event: str) -> None:
        self._events.append({"ts": _utcnow(), "event": event})
        logger.info("vpn event: %s", event)

    # --- stale-process record -----------------------------------------

    def _marker_path(self) -> Path:
        return self._state_dir / "active.json"

    def _write_marker(self) -> None:
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "pid": getattr(self._proc, "pid", None),
                "profile_dir": str(self._profile_dir or ""),
                "started_at": _utcnow(),
            }
            self._marker_path().write_text(
                json.dumps(payload, sort_keys=True), encoding="utf-8")
        except OSError:
            logger.warning("could not write VPN process marker")

    def _clear_marker(self) -> None:
        try:
            self._marker_path().unlink(missing_ok=True)
        except OSError:
            pass

    def _reap_stale(self) -> None:
        """Best-effort reaping of a process recorded by a previous server."""
        marker = self._marker_path()
        try:
            if not marker.is_file():
                return
            data = json.loads(marker.read_text(encoding="utf-8"))
            pid = int(data.get("pid") or 0)
            profile_dir = str(data.get("profile_dir") or "")
        except (OSError, ValueError, TypeError):
            self._clear_marker()
            return
        if pid and profile_dir and _pid_is_openvpn(pid, profile_dir):
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (AttributeError, OSError):
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
            logger.warning("reaped stale OpenVPN process pid=%s", pid)
        elif pid:
            logger.warning(
                "stale VPN marker present but process identity could not be "
                "verified; leaving it alone (pid=%s)", pid)
        self._clear_marker()


_manager_singleton: Optional[VPNManager] = None
_manager_lock = threading.Lock()


def get_vpn_manager() -> VPNManager:
    """Return the process-wide VPN manager (single active connection)."""
    global _manager_singleton
    with _manager_lock:
        if _manager_singleton is None:
            _manager_singleton = VPNManager()
            atexit.register(_manager_singleton.shutdown)
        return _manager_singleton


def set_vpn_manager(manager: Optional[VPNManager]) -> None:
    """Replace the singleton (tests / advanced embedding)."""
    global _manager_singleton
    with _manager_lock:
        _manager_singleton = manager


__all__ = [
    "DEFAULT_OPENVPN_BIN",
    "DEFAULT_STATE_ROOT",
    "OPENVPN_BIN_ENV",
    "VPNConflict",
    "VPNError",
    "VPNExecutableNotFound",
    "VPNManager",
    "VPNProfileError",
    "get_vpn_manager",
    "set_vpn_manager",
]
