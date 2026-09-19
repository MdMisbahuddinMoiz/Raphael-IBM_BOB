"""raphael_ibm_bob.c1a_transport — bounded subprocess transport for C1A.

Spawns one fixed argv (no shell), collects stdout/stderr with byte caps
DURING collection, and implements a real timeout -> kill -> drain sequence.

Guarantees:

    * ``subprocess.run(timeout=...)`` is NOT used as the cancellation
      primitive; the process is spawned in its own session and killed via
      the process group, then observed to have exited.
    * A timeout NEVER becomes success.
    * Output that arrives after the deadline is flagged ``late_output`` and
      NEVER becomes success.
    * Truncation is recorded, never silent.

POSIX-oriented (the RAPHAEL sandbox substrate is Linux). On non-POSIX the
process is killed directly.
"""
from __future__ import annotations

import math
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence


class TransportError(Exception):
    """Fail-closed transport error (never carries provider authority)."""


@dataclass(frozen=True)
class TransportResult:
    """Result of one bounded transport invocation."""
    stdout_bytes: bytes
    stderr_bytes: bytes
    exit_code: Optional[int]
    timed_out: bool
    late_output: bool
    killed: bool
    drain_completed: bool
    process_exited: bool
    elapsed_seconds: float
    stdout_truncated: bool
    stderr_truncated: bool

    def receipt_ok(self) -> bool:
        """True only for a clean, complete, on-time, zero-exit receipt."""
        return (not self.timed_out
                and not self.late_output
                and self.process_exited
                and self.exit_code == 0
                and not self.stdout_truncated
                and not self.stderr_truncated)


class BoundedTransport:
    """Bounded subprocess transport with proper timeout/kill/drain."""

    def __init__(self, *, max_stdout_bytes: int = 65536,
                 max_stderr_bytes: int = 8192,
                 drain_timeout_seconds: float = 5.0):
        for name, value in (("max_stdout_bytes", max_stdout_bytes),
                            ("max_stderr_bytes", max_stderr_bytes),
                            ("drain_timeout_seconds", drain_timeout_seconds)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TransportError(f"{name} must be numeric")
            if not math.isfinite(float(value)) or value <= 0:
                raise TransportError(f"{name} must be finite and positive")
        self._max_stdout = int(max_stdout_bytes)
        self._max_stderr = int(max_stderr_bytes)
        self._drain_timeout = float(drain_timeout_seconds)

    # --- public API -------------------------------------------------------

    def execute(
        self,
        argv: Sequence[str],
        timeout_seconds: float,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> TransportResult:
        if not argv or not all(
                isinstance(a, str) and a for a in argv):
            raise TransportError("argv must be a non-empty list of strings")
        if (isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(float(timeout_seconds))
                or timeout_seconds <= 0):
            raise TransportError("timeout_seconds must be finite and positive")

        try:
            process = subprocess.Popen(
                list(argv),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env if env is not None else {},
                cwd=cwd,
                start_new_session=True,
            )
        except OSError as exc:
            raise TransportError(
                f"failed to spawn process: {type(exc).__name__}:{exc}") from exc

        state: Dict[str, bool] = {"deadline_exceeded": False,
                                  "late_output": False}
        lock = threading.Lock()
        out_store: Dict[str, object] = {"buf": bytearray(), "truncated": False}
        err_store: Dict[str, object] = {"buf": bytearray(), "truncated": False}

        def _reader(stream, store, cap: int) -> None:
            try:
                while True:
                    chunk = stream.read(4096)
                    if not chunk:
                        break
                    with lock:
                        if state["deadline_exceeded"]:
                            state["late_output"] = True
                    buf = store["buf"]
                    if len(buf) + len(chunk) > cap:
                        remaining = max(0, cap - len(buf))
                        buf.extend(chunk[:remaining])
                        store["truncated"] = True
                    else:
                        buf.extend(chunk)
            except (ValueError, OSError):
                return
            finally:
                try:
                    stream.close()
                except OSError:
                    pass

        reader_out = threading.Thread(
            target=_reader, args=(process.stdout, out_store, self._max_stdout),
            daemon=True)
        reader_err = threading.Thread(
            target=_reader, args=(process.stderr, err_store, self._max_stderr),
            daemon=True)
        start = time.monotonic()
        reader_out.start()
        reader_err.start()

        timed_out = False
        drain_completed = True
        try:
            process.wait(timeout=float(timeout_seconds))
        except subprocess.TimeoutExpired:
            timed_out = True
            with lock:
                state["deadline_exceeded"] = True
            self._kill(process)
            drain_deadline = time.monotonic() + self._drain_timeout
            while time.monotonic() < drain_deadline:
                if process.poll() is not None:
                    break
                time.sleep(0.01)
            drain_completed = process.poll() is not None

        reader_out.join(timeout=self._drain_timeout)
        reader_err.join(timeout=self._drain_timeout)
        elapsed = time.monotonic() - start
        process_exited = process.poll() is not None
        with lock:
            late_output = state["late_output"]

        return TransportResult(
            stdout_bytes=bytes(out_store["buf"]),
            stderr_bytes=bytes(err_store["buf"]),
            exit_code=process.returncode,
            timed_out=timed_out,
            late_output=late_output,
            killed=timed_out,
            drain_completed=drain_completed,
            process_exited=process_exited,
            elapsed_seconds=elapsed,
            stdout_truncated=bool(out_store["truncated"]),
            stderr_truncated=bool(err_store["truncated"]),
        )

    # --- internals --------------------------------------------------------

    @staticmethod
    def _kill(process: "subprocess.Popen") -> None:
        if os.name == "posix":
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                return
            except (ProcessLookupError, PermissionError, OSError):
                pass
        try:
            process.kill()
        except (ProcessLookupError, OSError):
            pass


__all__ = ["BoundedTransport", "TransportError", "TransportResult"]
