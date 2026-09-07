"""raphael_bob.workspace — isolated workspace root for the BOB MVP.

The MVP capabilities operate only on files that resolve inside a declared
workspace root. The Workspace object is the canonical authority for
"is this path inside the scope?" decisions and provides realpath
canonicalization to defeat `..` traversal.

This module is deliberately small. It carries no business logic.
"""
from __future__ import annotations

import os
from pathlib import Path


class Workspace:
    """An isolated workspace root.

    All M2 capability checks resolve `target` against this root. The root
    itself must exist and be a directory at construction time. Paths that
    escape the root via `..` or symlinks are rejected.
    """

    def __init__(self, root: str | os.PathLike[str]):
        p = Path(root).resolve(strict=True)
        if not p.is_dir():
            raise ValueError(f"workspace root must be a directory: {p}")
        self._root = p

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, target: str) -> Path:
        """Resolve `target` to an absolute path; raise if it escapes the root.

        Accepts both absolute paths (which must be inside the root) and
        relative paths (which are joined to the root). Returns the
        canonical absolute path.
        """
        t = Path(target)
        if t.is_absolute():
            candidate = t.resolve()
        else:
            candidate = (self._root / t).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as e:
            raise PermissionError(
                f"target escapes workspace: {candidate} not under {self._root}"
            ) from e
        return candidate

    def is_within(self, target: str) -> bool:
        """Best-effort containment check without raising on escape."""
        try:
            self.resolve(target)
            return True
        except (PermissionError, FileNotFoundError):
            return False

    def __repr__(self) -> str:
        return f"Workspace({self._root!s})"


__all__ = ["Workspace"]