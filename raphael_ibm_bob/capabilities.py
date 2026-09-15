"""raphael_ibm_bob.capabilities — MVP capability implementations.

Each capability is a pure function over `(workspace, request) -> result_dict`.
The Broker invokes a capability only after Policy ALLOWs. Capabilities
themselves do NOT consult the Policy (separation of concerns); the
Broker is the single consultation point.

Implemented capabilities:
    READ      - read a regular file inside the workspace.
    LIST      - list a directory inside the workspace.
    SEARCH    - grep-search a directory inside the workspace.
    WRITE     - write a file inside the workspace.
    RUN_TEST  - invoke `python3 -m unittest <module>` for a single test file.

Network access: NONE.
Process execution: ONLY for RUN_TEST, scoped to `python3 -m unittest`.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from raphael_ibm_bob.contracts import ActionRequest, Capability
from raphael_ibm_bob.workspace import Workspace


def _read(workspace: Workspace, request: ActionRequest) -> Dict[str, Any]:
    p = workspace.resolve(request.target)
    return {"path": str(p), "content": p.read_text(encoding="utf-8", errors="replace")}


def _list(workspace: Workspace, request: ActionRequest) -> Dict[str, Any]:
    p = workspace.resolve(request.target)
    entries = sorted(e.name for e in p.iterdir())
    return {"path": str(p), "entries": entries}


def _search(workspace: Workspace, request: ActionRequest) -> Dict[str, Any]:
    p = workspace.resolve(request.target)
    pattern = request.purpose  # SEARCH uses `purpose` as the search pattern
    if not pattern:
        return {"path": str(p), "matches": []}
    rx = re.compile(pattern)
    matches: list[Dict[str, Any]] = []
    for path in p.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if rx.search(line):
                matches.append({"file": str(path), "line": i, "text": line[:200]})
    return {"path": str(p), "matches": matches}


def _write(workspace: Workspace, request: ActionRequest) -> Dict[str, Any]:
    p = workspace.resolve(request.target)
    # WRITE's payload is a base64-ish utf-8 string. For MVP, callers pass
    # the content in `request.purpose` after a marker `content=`; this is
    # deliberately minimal so M3 can replace it with a structured payload.
    prefix = "content="
    if not request.purpose.startswith(prefix):
        raise ValueError("WRITE request must carry content in purpose='content=...'")
    content = request.purpose[len(prefix):]
    p.write_text(content, encoding="utf-8")
    return {"path": str(p), "bytes": len(content.encode("utf-8"))}


def _run_test(workspace: Workspace, request: ActionRequest) -> Dict[str, Any]:
    """Run a single named test file via `python3 -m unittest`.

    The test file MUST be importable as a module whose name is its
    filesystem path with `/` replaced by `.` and `.py` stripped. To keep
    this MVP-correct without relying on sys.path manipulation, we set
    PYTHONPATH to the workspace root and run `python3 -m unittest
    <dotted.module>`. The test file is required to live inside the
    workspace and match the test_*.py / *_test.py pattern.

    T1-4: the execution bound is `request.timeout_seconds` when set,
    else the 30s broker default. A timeout is reported as an explicit
    `{"timeout": True, ...}` payload with partial output preserved —
    never as success, never as a DENY (the decision was ALLOW).
    """
    p = workspace.resolve(request.target)
    rel = p.relative_to(workspace.root).with_suffix("")
    module = ".".join(rel.parts)
    timeout = (request.timeout_seconds
               if request.timeout_seconds is not None else 30.0)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(workspace.root) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", module, "-v"],
            cwd=str(workspace.root),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        # Partial output may arrive as bytes or str depending on how
        # the interpreter was killed; normalize defensively so the
        # evidence payload stays JSON-serializable for the ledger.
        def _text(value: object) -> str:
            if value is None:
                return ""
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            return str(value)
        return {
            "timeout": True,
            "timeout_seconds": timeout,
            "module": module,
            "returncode": None,
            "partial_stdout": _text(exc.stdout)[-2000:],
            "partial_stderr": _text(exc.stderr)[-2000:],
        }
    return {
        "module": module,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


CAPABILITY_DISPATCH = {
    Capability.READ: _read,
    Capability.LIST: _list,
    Capability.SEARCH: _search,
    Capability.WRITE: _write,
    Capability.RUN_TEST: _run_test,
}


def execute_capability(workspace: Workspace, request: ActionRequest) -> Dict[str, Any]:
    """Dispatch an allowed request to its capability implementation.

    The Broker guarantees that this function is reached only after
    Policy ALLOW. Capabilities themselves do NOT re-consult Policy.
    """
    handler = CAPABILITY_DISPATCH.get(request.capability)
    if handler is None:
        raise ValueError(f"no capability handler for {request.capability}")
    return handler(workspace, request)


__all__ = ["execute_capability"]