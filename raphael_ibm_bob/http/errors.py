"""raphael_ibm_bob.http.errors — structured HTTP errors.

A tiny, dependency-free error type plus the canonical error codes used
by the presentation layer. Errors carry a stable machine code and a
human message; they never carry credentials, headers, or stack traces.
"""
from __future__ import annotations

from typing import Optional


class ApiError(Exception):
    """A structured HTTP error.

    `status` is the HTTP status; `code` is a stable machine-readable
    identifier; `message` is a safe, human-readable string. Nothing
    here may include secrets or internal stack traces.
    """

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message

    def to_body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}


# Canonical error codes (stable identifiers for clients).
BAD_REQUEST = "BAD_REQUEST"
INVALID_INPUT = "INVALID_INPUT"
NOT_FOUND = "NOT_FOUND"
SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
RUN_NOT_FOUND = "RUN_NOT_FOUND"
WORKSPACE_NOT_FOUND = "WORKSPACE_NOT_FOUND"
TASK_NOT_FOUND = "TASK_NOT_FOUND"
ROLE_NOT_FOUND = "ROLE_NOT_FOUND"
METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
CONFLICT = "CONFLICT"
RUN_NOT_CANCELLABLE = "RUN_NOT_CANCELLABLE"
RUN_TERMINAL = "RUN_TERMINAL"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
UNAUTHORIZED = "UNAUTHORIZED"
FORBIDDEN_HOST = "FORBIDDEN_HOST"
INVALID_ORIGIN = "INVALID_ORIGIN"
CSRF_REJECTED = "CSRF_REJECTED"
MODEL_NOT_CONFIGURED = "MODEL_NOT_CONFIGURED"
INTERNAL_ERROR = "INTERNAL_ERROR"


def not_found(code: str, message: str) -> ApiError:
    return ApiError(404, code, message)


def bad_request(message: str,
                code: Optional[str] = None) -> ApiError:
    return ApiError(400, code or BAD_REQUEST, message)


def invalid_input(message: str) -> ApiError:
    return ApiError(422, INVALID_INPUT, message)


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


__all__ = [
    "ApiError",
    "BAD_REQUEST",
    "CONFLICT",
    "CSRF_REJECTED",
    "FORBIDDEN_HOST",
    "INVALID_INPUT",
    "INVALID_ORIGIN",
    "INTERNAL_ERROR",
    "METHOD_NOT_ALLOWED",
    "MODEL_NOT_CONFIGURED",
    "NOT_FOUND",
    "PAYLOAD_TOO_LARGE",
    "ROLE_NOT_FOUND",
    "RUN_NOT_CANCELLABLE",
    "RUN_NOT_FOUND",
    "RUN_TERMINAL",
    "SESSION_NOT_FOUND",
    "TASK_NOT_FOUND",
    "UNAUTHORIZED",
    "WORKSPACE_NOT_FOUND",
    "bad_request",
    "conflict",
    "invalid_input",
    "not_found",
]
