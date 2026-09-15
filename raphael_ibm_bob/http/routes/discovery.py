"""Discovery routes — read-only M14 catalog (never a second registry)."""
from __future__ import annotations

from typing import Optional

from raphael_ibm_bob.contracts import Capability
from raphael_ibm_bob.harness import api
from raphael_ibm_bob.http import errors, schemas


def _parse_capability(raw: str) -> Capability:
    candidate = raw.strip()
    try:
        return Capability(candidate)
    except ValueError:
        for member in Capability:
            if member.value.lower() == candidate.lower() or \
                    member.name.lower() == candidate.lower():
                return member
    raise errors.invalid_input(f"unknown capability: {raw}")


def _optional_role(request) -> Optional[str]:
    return request.query_one("role")


def list_roles(request, params, config):
    return {"roles": [schemas.role_json(r) for r in api.list_roles()]}


def list_capabilities(request, params, config):
    role = _optional_role(request)
    try:
        definitions = api.list_capabilities(role)
    except KeyError as exc:
        raise errors.not_found(errors.ROLE_NOT_FOUND, str(exc)) from None
    return {"capabilities": [schemas.capability_json(d)
                             for d in definitions]}


def list_skills(request, params, config):
    role = _optional_role(request)
    capability_raw = request.query_one("capability")
    capability = (_parse_capability(capability_raw)
                  if capability_raw is not None else None)
    evidence_available = tuple(
        kind
        for value in request.query.get("evidence_available", [])
        for kind in value.split(",") if kind)
    try:
        skills = api.list_skills(role=role, capability=capability,
                                 evidence_available=evidence_available)
    except KeyError as exc:
        raise errors.not_found(errors.ROLE_NOT_FOUND, str(exc)) from None
    return {"skills": [schemas.skill_json(s) for s in skills]}


__all__ = ["list_capabilities", "list_roles", "list_skills"]
