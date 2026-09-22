"""raphael_ibm_bob.skills — T1-1 declared capability + skill registry.

Adapted concepts (not copied code):
- Decepticon `ToolProtocol` + skills registry
  (`packages/decepticon-core/.../protocols/tool.py`,
  `.../registry/skills.py`, `packages/decepticon/.../tools/skills.py`):
  a declared contract (id/version/description) separate from execution.
- DeepSeek `defineTool` + skill bundles
  (`packages/core/tools/`, `packages/skill/skill-filesystem/`):
  schema + description + versioned, discoverable definitions.

Deliberately NOT imported: plugin loaders, marketplaces, remote
registries, lifecycle frameworks, model-routing. This registry is an
in-process declaration index only.

Hard rule: declarations are NOT authorization. A skill proposal
produces an ordinary `ActionRequest` that still travels
Runtime -> Broker -> Policy. A declared skill never implies permission.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from raphael_ibm_bob.contracts import ActionRequest, Capability
from raphael_ibm_bob.falsifier import ChallengeSpec
from raphael_ibm_bob.specialization import RoleRegistry, default_roles


_VERSION_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")


def _check_version(version: str, what: str) -> str:
    if not isinstance(version, str) or not _VERSION_RE.match(version):
        raise ValueError(
            f"{what} version must look like MAJOR.MINOR[.PATCH], "
            f"got {version!r}")
    return version


def _version_key(version: str) -> Tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


@dataclass(frozen=True)
class CapabilityDefinition:
    """Declares what one BOB capability is for (description only).

    `purpose_template` must contain a `{target}` placeholder so
    proposals render deterministically. `verification_expectation`
    documents what a retest should observe (fed to the Verifier by
    the caller, never executed here). `timeout_seconds` is the
    suggested execution bound consumed by the T1-4 timeout path;
    None means the broker default for the capability.

    M14: `evidence_produced` / `evidence_consumed` declare the
    capability's evidence *shape* (a contract, not a permission).
    """
    capability: Capability
    description: str
    target_schema: str
    purpose_template: str
    verification_expectation: Optional[str] = None
    version: str = "1.0"
    timeout_seconds: Optional[float] = None
    evidence_produced: Tuple[str, ...] = ()
    evidence_consumed: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.capability, Capability):
            raise ValueError(
                f"capability must be a Capability enum member, "
                f"got {self.capability!r}")
        if not self.description:
            raise ValueError("description is required")
        if "{target}" not in self.purpose_template:
            raise ValueError(
                "purpose_template must contain a {target} placeholder")
        _check_version(self.version, "CapabilityDefinition")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        for kind in self.evidence_produced + self.evidence_consumed:
            if not kind:
                raise ValueError("evidence kind names must be non-empty")


@dataclass(frozen=True)
class SkillDefinition:
    """A named, versioned usage recipe over one capability.

    `success_markers` are substrings the Verifier should observe;
    `challenge` (optional) is a template-free ChallengeSpec the
    Falsifier may run — both feed the EXISTING Verifier/Falsifier,
    never a new framework. `predicate` callables inside `challenge`
    are intentionally discouraged for stored skills (they do not
    survive any serialization); prefer `forbidden_substring`.

    M14: `role` binds the skill to one declared specialist role;
    `evidence_produced` / `evidence_consumed` declare its evidence
    contract; `prerequisites` names skills that must exist first.
    None of these grant authority — proposals still go through the
    Broker/Policy boundary.
    """
    id: str
    name: str
    version: str
    description: str
    capability: Capability
    target_schema: str
    purpose_template: str
    success_markers: Tuple[str, ...] = ()
    challenge: Optional[ChallengeSpec] = None
    role: Optional[str] = None
    evidence_produced: Tuple[str, ...] = ()
    evidence_consumed: Tuple[str, ...] = ()
    prerequisites: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id or not self.name:
            raise ValueError("skill id and name are required")
        if not isinstance(self.capability, Capability):
            raise ValueError(
                f"capability must be a Capability enum member, "
                f"got {self.capability!r}")
        if "{target}" not in self.purpose_template:
            raise ValueError(
                "purpose_template must contain a {target} placeholder")
        _check_version(self.version, f"SkillDefinition({self.id})")
        for marker in self.success_markers:
            if not marker:
                raise ValueError("success_markers must be non-empty")
        if self.role is not None and not self.role:
            raise ValueError("role must be a non-empty id or None")
        for name in (self.evidence_produced + self.evidence_consumed
                     + self.prerequisites):
            if not name:
                raise ValueError("evidence/prerequisite names must be "
                                 "non-empty")


@dataclass(frozen=True)
class SkillProposal:
    """A validated skill proposal and the ActionRequest it builds."""
    request: ActionRequest
    skill_id: str
    skill_version: str

    def to_evidence_payload(self) -> Dict[str, object]:
        return {
            "kind": "skill-proposal",
            "skill_id": self.skill_id,
            "skill_version": self.skill_version,
            "capability": self.request.capability.value,
            "target": self.request.target,
            "purpose": self.request.purpose,
        }


class CapabilityRegistry:
    """In-process declaration index for capabilities and skills.

    Also the single authority for role-aware discovery (M14): roles
    are declared, skills may reference one, and discovery is
    read-only. Declarations grant no authority.
    """

    def __init__(self, roles: Optional[RoleRegistry] = None) -> None:
        self._capabilities: Dict[str, CapabilityDefinition] = {}
        self._skills: Dict[str, SkillDefinition] = {}
        self._roles: RoleRegistry = roles or default_roles()

    # --- capabilities -------------------------------------------------

    def register_capability(self, definition: CapabilityDefinition) -> None:
        key = definition.capability.value
        existing = self._capabilities.get(key)
        if existing is not None and existing.version == definition.version:
            raise ValueError(
                f"duplicate capability definition: {key} "
                f"version {definition.version}")
        if (existing is not None
                and _version_key(definition.version)
                <= _version_key(existing.version)):
            raise ValueError(
                f"capability {key} version {definition.version} does not "
                f"supersede registered {existing.version}")
        self._capabilities[key] = definition

    def lookup_capability(
            self, capability: Capability) -> CapabilityDefinition:
        try:
            return self._capabilities[capability.value]
        except KeyError:
            raise KeyError(
                f"capability not registered: {capability!r}") from None

    def list_capabilities(self) -> List[CapabilityDefinition]:
        return [self._capabilities[k] for k in sorted(self._capabilities)]

    # --- skills ---------------------------------------------------------

    def register_skill(self, skill: SkillDefinition) -> None:
        if skill.id in self._skills and \
                self._skills[skill.id].version == skill.version:
            raise ValueError(
                f"duplicate skill: {skill.id} version {skill.version}")
        if skill.id in self._skills and _version_key(skill.version) <= \
                _version_key(self._skills[skill.id].version):
            raise ValueError(
                f"skill {skill.id} version {skill.version} does not "
                f"supersede registered {self._skills[skill.id].version}")
        # Compatibility: the skill's capability should be declared so
        # proposals inherit timeout/verification defaults.
        if skill.capability.value not in self._capabilities:
            raise ValueError(
                f"skill {skill.id} uses undeclared capability "
                f"{skill.capability.value!r}: register the capability first")
        # M14: role must be known and compatible with the capability.
        if skill.role is not None:
            try:
                role = self._roles.get_role(skill.role)
            except KeyError:
                raise ValueError(
                    f"skill {skill.id} references unknown role "
                    f"{skill.role!r}") from None
            if skill.capability not in role.capabilities:
                raise ValueError(
                    f"skill {skill.id} capability "
                    f"{skill.capability.value!r} is not compatible with "
                    f"role {skill.role!r} (role declares "
                    f"{sorted(c.value for c in role.capabilities)})")
        for prereq in skill.prerequisites:
            if prereq not in self._skills:
                raise ValueError(
                    f"skill {skill.id} prerequisite not registered: "
                    f"{prereq!r}")
        self._skills[skill.id] = skill

    def has_skill(self, skill_id: str) -> bool:
        """Whether any version of the skill id is registered."""
        return skill_id in self._skills

    def lookup_skill(self, skill_id: str,
                     version: Optional[str] = None) -> SkillDefinition:
        try:
            skill = self._skills[skill_id]
        except KeyError:
            raise KeyError(
                f"skill not registered: {skill_id!r}") from None
        if version is not None and skill.version != version:
            raise KeyError(
                f"skill {skill_id!r} has no version {version!r} "
                f"(registered: {skill.version})")
        return skill

    def list_skills(self) -> List[SkillDefinition]:
        return [self._skills[k] for k in sorted(self._skills)]

    # --- role-aware discovery (M14, read-only) ----------------------------

    def list_roles(self) -> list:
        """All declared specialist roles, sorted by id."""
        return self._roles.list_roles()

    def get_role(self, role_id: str):
        """Look up a declared role (KeyError if unknown)."""
        return self._roles.get_role(role_id)

    def list_skills_for_role(self, role_id: str) -> List[SkillDefinition]:
        """Declared skills bound to a role (KeyError if role unknown)."""
        self._roles.get_role(role_id)  # validate role exists
        return [s for s in self.list_skills() if s.role == role_id]

    def list_capabilities_for_role(self, role_id: str) -> List[Capability]:
        """Capabilities a role declares it is meant to use."""
        role = self._roles.get_role(role_id)
        return sorted(role.capabilities, key=lambda c: c.value)

    def discover_skills(self, *, role: Optional[str] = None,
                        capability: Optional[Capability] = None,
                        evidence_available: Tuple[str, ...] = ()
                        ) -> List[SkillDefinition]:
        """Read-only discovery of declared skills.

        Filters by role and/or capability; only returns skills whose
        declared prerequisites are satisfied and whose consumed
        evidence is available (when the caller supplies it). This
        grants nothing: the returned skills still produce ordinary
        ActionRequests gated by Broker/Policy.
        """
        if role is not None:
            self._roles.get_role(role)  # validate role exists
        if capability is not None and \
                not isinstance(capability, Capability):
            raise ValueError("capability must be a Capability member")
        available = set(evidence_available)
        out: List[SkillDefinition] = []
        for skill in self.list_skills():
            if role is not None and skill.role != role:
                continue
            if capability is not None and skill.capability != capability:
                continue
            if any(p not in self._skills for p in skill.prerequisites):
                continue
            consumed = set(skill.evidence_consumed)
            if available and not consumed.issubset(available):
                continue
            out.append(skill)
        return out

    # --- proposals --------------------------------------------------------

    def propose(self, skill_id: str, target: str, *,
                requester: Optional[str] = None,
                plan_id: Optional[str] = None,
                finding_id: Optional[str] = None,
                timeout_seconds: Optional[float] = None,
                version: Optional[str] = None) -> SkillProposal:
        """Build an ordinary ActionRequest from a registered skill.

        The execution bound defaults to the skill capability's declared
        `timeout_seconds`; an explicit positive override wins. The
        request carries no authority: submit it through
        Runtime/Broker/Policy, which enforces the bound.
        """
        skill = self.lookup_skill(skill_id, version=version)
        if not target:
            raise ValueError("proposal target is required")
        cap_def = self._capabilities.get(skill.capability.value)
        timeout = timeout_seconds
        if timeout is None and cap_def is not None:
            timeout = cap_def.timeout_seconds
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout_seconds must be positive")
        request = ActionRequest(
            sequence=0,
            requester=requester or f"skill:{skill.id}",
            capability=skill.capability,
            target=target,
            purpose=skill.purpose_template.format(target=target),
            plan_id=plan_id,
            finding_id=finding_id,
            timeout_seconds=timeout,
        )
        return SkillProposal(
            request=request,
            skill_id=skill.id,
            skill_version=skill.version,
        )


def default_registry() -> CapabilityRegistry:
    """Registry preloaded with the five authoritative BOB capabilities."""
    registry = CapabilityRegistry()
    registry.register_capability(CapabilityDefinition(
        capability=Capability.READ,
        description="Read a regular file inside the workspace.",
        target_schema="relative file path inside the workspace",
        purpose_template="skill:read:{target}",
        verification_expectation="expected marker substring present",
        version="1.0",
        evidence_produced=("inspection",),
    ))
    registry.register_capability(CapabilityDefinition(
        capability=Capability.LIST,
        description="List a directory inside the workspace.",
        target_schema="relative directory path inside the workspace",
        purpose_template="skill:list:{target}",
        version="1.0",
        evidence_produced=("inspection",),
    ))
    registry.register_capability(CapabilityDefinition(
        capability=Capability.SEARCH,
        description="Regex-search a directory; pattern in purpose.",
        target_schema="relative directory path inside the workspace",
        purpose_template="skill:search:{target}",
        version="1.0",
        evidence_produced=("inspection",),
    ))
    registry.register_capability(CapabilityDefinition(
        capability=Capability.WRITE,
        description="Write a file; content carried as purpose content=...",
        target_schema="relative file path with existing parent",
        purpose_template="skill:write:{target}",
        version="1.0",
        evidence_produced=("remediation",),
        evidence_consumed=("inspection",),
    ))
    registry.register_capability(CapabilityDefinition(
        capability=Capability.RUN_TEST,
        description="Run one test file via unittest; must match test shape.",
        target_schema="test_*.py or *_test.py inside the workspace",
        purpose_template="skill:required-test:{target}",
        verification_expectation="returncode 0",
        version="1.0",
        timeout_seconds=30.0,
        evidence_produced=("test-execution",),
    ))
    registry.register_capability(CapabilityDefinition(
        capability=Capability.NETWORK_HTTP_REQUEST,
        description=("One governed HTTP(S) GET/HEAD request to an authorized "
                     "target (D9)."),
        target_schema="http(s) URL inside the declared TargetProfile scope",
        purpose_template="network-http-request:{target}",
        verification_expectation=("an independent governed request yields the "
                                  "same flag hash"),
        version="1.0",
        timeout_seconds=10.0,
        evidence_produced=("network-observation",),
    ))
    return registry


_DEFAULT_SKILLS = (
    ("read-file", "Read a file", Capability.READ, "investigator",
     ("inspection",), ()),
    ("list-dir", "List a directory", Capability.LIST, "investigator",
     ("inspection",), ()),
    ("search-dir", "Regex-search a directory", Capability.SEARCH,
     "investigator", ("inspection",), ()),
    ("write-file", "Write a file", Capability.WRITE,
     "remediation_planner", ("remediation",), ("inspection",)),
    ("run-test", "Run a named test file", Capability.RUN_TEST,
     "test_analyst", ("test-execution",), ()),
    ("network-http-request", "Governed HTTP request",
     Capability.NETWORK_HTTP_REQUEST, None,
     ("network-observation",), ()),
)


def register_default_skills(
        registry: CapabilityRegistry) -> CapabilityRegistry:
    """Register one generic skill per declared capability.

    Scenario-neutral presentation primitives for model-driven paths
    (e.g. the Harness CLI): the skill id names the operation, the
    capability gates execution. M14 binds each skill to a specialist
    role and declares its evidence contract. Existing ids are left
    untouched so repeated calls are idempotent.
    """
    for skill_id, name, capability, role, produced, consumed in \
            _DEFAULT_SKILLS:
        if registry.has_skill(skill_id):
            continue
        definition = registry.lookup_capability(capability)
        registry.register_skill(SkillDefinition(
            id=skill_id,
            name=name,
            version="1.0",
            description=definition.description,
            capability=capability,
            target_schema=definition.target_schema,
            purpose_template=f"{skill_id}:{{target}}",
            role=role,
            evidence_produced=produced,
            evidence_consumed=consumed,
        ))
    return registry


__all__ = [
    "CapabilityDefinition",
    "SkillDefinition",
    "SkillProposal",
    "CapabilityRegistry",
    "default_registry",
    "register_default_skills",
]
