"""OpenAI-compatible HTTP provider adapter (stdlib only).

Speaks `POST {endpoint}/chat/completions` with a JSON-mode system
contract and parses ONE structured proposal per call:

    {"intent": "act", "skill": "<skill-id>",
     "target": "<target>", "purpose": "<why>"}
    {"intent": "act", "skill": "write-file", "target": "<path>",
     "purpose": "<why>", "content": "<complete file text>"}
    {"intent": "done"}

The proposal is validated against the T1-1 registry (skill exists,
capability declared, target/purpose present) and built with
`registry.propose` — the SAME constructor scripted paths use. The
adapter returns an `ActionRequest`; authorization still happens
exclusively in Runtime -> Broker -> Policy.

Failure taxonomy (all explicit, all carry redacted detail):
- `ProviderConfigError`  missing endpoint/model configuration
- `ProviderTimeout`      HTTP timeout (urllib) exceeded
- `ProviderError`        transport/HTTP-status/provider-payload errors
- `StructuredProposalError`  non-JSON, wrong shape, unknown skill,
  empty target/purpose, unknown intent
- `ProviderCancelled`    cooperative cancel before dispatch
"""
from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from raphael_ibm_bob.contracts import ActionRequest, Capability
from raphael_ibm_bob.harness.model import ModelContext
from raphael_ibm_bob.skills import CapabilityRegistry

ENDPOINT_ENV = "RAPHAEL_MODEL_ENDPOINT"
API_KEY_ENV = "RAPHAEL_MODEL_API_KEY"
MODEL_ENV = "RAPHAEL_MODEL_NAME"

# Honest client identification. Some edges (Cloudflare bot
# management: error 1010) reject the default python-urllib signature
# outright; identifying as our own client is required for the call to
# be evaluated at all. This is not auth and not spoofing.
USER_AGENT = "RaphaelHarness/1.0"

_VALID_INTENTS = ("act", "done")


class ProviderConfigError(Exception):
    """Endpoint/model configuration missing or invalid."""


class ProviderError(Exception):
    """Transport, HTTP-status, or provider-payload failure."""


class ProviderTimeout(ProviderError):
    """The HTTP call exceeded the configured bound."""


class ProviderCancelled(ProviderError):
    """Cancelled cooperatively before dispatch."""


class StructuredProposalError(Exception):
    """Model output failed structural validation (never executed)."""


class DoneSignal(Exception):
    """Model declared intent=done: terminal signal, not a failure and
    not an action. The turn loop stops; nothing is submitted."""


@dataclass(frozen=True)
class OpenAICompatConfig:
    """Connection parameters. The key is write-only in practice:
    stored for header construction, never rendered anywhere."""
    endpoint: str
    model: str
    api_key: str = ""
    timeout_seconds: float = 30.0
    max_tokens: int = 512
    temperature: float = 0.0
    extra_body: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.endpoint.startswith(("http://", "https://")):
            raise ProviderConfigError(
                "endpoint must be an http(s) URL")
        if not self.model:
            raise ProviderConfigError("model name is required")
        if self.timeout_seconds <= 0:
            raise ProviderConfigError("timeout_seconds must be positive")
        if not 0.0 <= self.temperature <= 2.0:
            raise ProviderConfigError(
                "temperature must be within 0.0..2.0")

    def redacted(self) -> Dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "max_tokens": self.max_tokens,
            "api_key": "set" if self.api_key else "unset",
        }


def config_from_env() -> OpenAICompatConfig:
    """Build config from the environment. Missing values raise
    ProviderConfigError naming the variable — values are never echoed."""
    endpoint = os.environ.get(ENDPOINT_ENV, "")
    model = os.environ.get(MODEL_ENV, "")
    missing = [name for value, name in ((endpoint, ENDPOINT_ENV),
                                          (model, MODEL_ENV)) if not value]
    if missing:
        raise ProviderConfigError(
            "missing model configuration: " + ", ".join(missing))
    timeout_raw = os.environ.get("RAPHAEL_MODEL_TIMEOUT", "30")
    try:
        timeout = float(timeout_raw)
    except ValueError:
        raise ProviderConfigError(
            "RAPHAEL_MODEL_TIMEOUT must be numeric") from None
    tokens_raw = os.environ.get("RAPHAEL_MODEL_MAX_TOKENS", "512")
    try:
        max_tokens = int(tokens_raw)
    except ValueError:
        raise ProviderConfigError(
            "RAPHAEL_MODEL_MAX_TOKENS must be an integer") from None
    if max_tokens < 1:
        raise ProviderConfigError(
            "RAPHAEL_MODEL_MAX_TOKENS must be positive")
    temp_raw = os.environ.get("RAPHAEL_MODEL_TEMPERATURE", "0")
    try:
        temperature = float(temp_raw)
    except ValueError:
        raise ProviderConfigError(
            "RAPHAEL_MODEL_TEMPERATURE must be numeric") from None
    extra_raw = os.environ.get("RAPHAEL_MODEL_EXTRA_BODY", "")
    extra_body: Dict[str, Any] = {}
    if extra_raw:
        try:
            parsed_extra = json.loads(extra_raw)
        except ValueError:
            raise ProviderConfigError(
                "RAPHAEL_MODEL_EXTRA_BODY must be a JSON object") from None
        if not isinstance(parsed_extra, dict):
            raise ProviderConfigError(
                "RAPHAEL_MODEL_EXTRA_BODY must be a JSON object")
        extra_body = parsed_extra
    return OpenAICompatConfig(
        endpoint=endpoint.rstrip("/"),
        model=model,
        api_key=os.environ.get(API_KEY_ENV, ""),
        timeout_seconds=timeout,
        max_tokens=max_tokens,
        temperature=temperature,
        extra_body=extra_body,
    )


def provider_from_env(name: str,
                      registry: CapabilityRegistry
                      ) -> "OpenAICompatAdapter":
    """Build a configured provider by name. Only 'openai-compatible'
    exists; anything else is an explicit error (no silent fallback).
    Configuration comes from the environment (see `config_from_env`);
    missing values raise before any request is made."""
    if name != "openai-compatible":
        raise ProviderConfigError(f"unknown provider: {name!r}")
    return OpenAICompatAdapter(config_from_env(), registry)


def skill_catalog(registry: CapabilityRegistry) -> List[Dict[str, str]]:
    """Render registry skills for model presentation.

    Derived from the registry on every call — never a parallel
    hardcoded list (Phase 7 requirement).
    """
    catalog = []
    for skill in registry.list_skills():
        catalog.append({
            "skill": skill.id,
            "capability": skill.capability.value,
            "description": skill.description,
            "target_schema": skill.target_schema,
        })
    return catalog


_SYSTEM_PROMPT = (
    "You propose exactly ONE next action for a governed coding agent. "
    "Reply with a single COMPACT JSON object and nothing else: no "
    "explanations, no commentary, no whitespace padding. Schema: "
    '{"intent": "act", "skill": "<skill-id from the catalog>", '
    '"target": "<concrete target>", "purpose": "<why>"} '
    'or {"intent": "done"} when the mission needs no further action. '
    "For the write-file skill ONLY, add "
    '"content": "<complete intended file text, max 8000 chars>; '
    "content is forbidden for every other skill. "
    "Never invent skills, capabilities, or targets outside the catalog. "
    "Do not repeat a capability and target combination already present "
    "in recent turns: build on observed outcomes instead. "
    "Work toward the mission each turn: inspect unknown files, run "
    "relevant tests, propose fixes for observed defects, verify fixes, "
    "then declare done. Act; do not stall re-reading known content."
)

#: Maximum model-supplied file content accepted for WRITE proposals.
MAX_CONTENT_CHARS = 8000


def build_request_body(config: OpenAICompatConfig, context: ModelContext,
                       catalog: List[Dict[str, str]]) -> Dict[str, Any]:
    """Pure request construction (unit-testable without network)."""
    user_content = json.dumps({
        "mission": context.summary(),
        "available_skills": catalog,
    }, sort_keys=True)
    body = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
    }
    for key, value in config.extra_body.items():
        # Provider-specific knobs (e.g. reasoning controls) ride along
        # without touching the governed fields above.
        if key not in body:
            body[key] = value
    return body


def parse_response_body(body: Dict[str, Any]) -> str:
    """Extract the assistant's JSON text or raise ProviderError."""
    try:
        choices = body["choices"]
        message = choices[0]["message"]
        content = message["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(
            f"provider response missing choices/message/content: {exc}"
        ) from None
    if not isinstance(content, str) or not content.strip():
        raise StructuredProposalError("empty model response")
    return content


def validate_proposal(data: Any,
                      registry: CapabilityRegistry) -> ActionRequest:
    """Validate structured output and build the ActionRequest.

    Every malformed shape raises StructuredProposalError and nothing
    is executed. Skill/target/purpose come from the model; permission
    still comes exclusively from Policy at submit time.
    """
    if not isinstance(data, dict):
        raise StructuredProposalError("proposal must be a JSON object")
    raw_intent = data.get("intent")
    skill_id = data.get("skill")
    # Lenient intent grammar (documented, deterministic): besides
    # "act"/"done", `intent` accepts a registered skill id, or a
    # capability value that the named skill must agree with. The
    # `skill` field is required except for the bare-skill-id form;
    # disagreement is ambiguous and rejected. Permission still comes
    # exclusively from Policy at submit time.
    if raw_intent == "done":
        raise DoneSignal("model declared done")
    elif raw_intent == "act":
        pass
    elif isinstance(raw_intent, str):
        try:
            registry.lookup_skill(raw_intent)
            if skill_id not in (None, "", raw_intent):
                raise StructuredProposalError(
                    "ambiguous proposal: intent names a different "
                    "skill than the skill field")
            skill_id = raw_intent
        except KeyError:
            if raw_intent not in {c.value for c in Capability}:
                raise StructuredProposalError(
                    f"intent must be one of {_VALID_INTENTS}, a "
                    f"registered skill id, or a capability value; "
                    f"got {str(raw_intent)[:80]}") from None
            if not isinstance(skill_id, str) or not skill_id:
                raise StructuredProposalError(
                    "capability intent requires the skill field")
            try:
                skill = registry.lookup_skill(skill_id)
            except KeyError:
                raise StructuredProposalError(
                    f"invalid skill: {skill_id!r}") from None
            if skill.capability.value != raw_intent:
                raise StructuredProposalError(
                    "ambiguous proposal: intent capability disagrees "
                    "with the skill's capability")
    else:
        raise StructuredProposalError(
            f"intent must be one of {_VALID_INTENTS}; "
            f"got {type(raw_intent).__name__}:"
            f"{str(raw_intent)[:80]}")
    target = data.get("target")
    purpose = data.get("purpose")
    content = data.get("content")
    if not isinstance(skill_id, str) or not skill_id:
        raise StructuredProposalError("missing skill id")
    if not isinstance(target, str) or not target:
        raise StructuredProposalError("missing target")
    if not isinstance(purpose, str) or not purpose:
        raise StructuredProposalError("missing purpose")
    try:
        proposal = registry.propose(skill_id, target)
    except (KeyError, ValueError) as exc:
        raise StructuredProposalError(f"invalid skill: {exc}") from None
    request = proposal.request
    if request.capability.value == "write":
        if not isinstance(content, str) or not content:
            raise StructuredProposalError(
                "WRITE proposals require content")
        if len(content) > MAX_CONTENT_CHARS:
            raise StructuredProposalError(
                f"content exceeds {MAX_CONTENT_CHARS} chars")
        # Boundary convention: WRITE carries content in purpose.
        purpose = "content=" + content
    elif content is not None:
        raise StructuredProposalError(
            "content is only allowed for WRITE proposals")
    final_purpose = (purpose if request.capability.value == "write"
                     else purpose[:500])
    return ActionRequest(
        sequence=request.sequence,
        requester=request.requester,
        capability=request.capability,
        target=request.target,
        purpose=final_purpose,
        plan_id=request.plan_id,
        finding_id=request.finding_id,
        timeout_seconds=request.timeout_seconds,
    )


class OpenAICompatAdapter:
    """Live OpenAI-compatible provider behind the ModelAdapter seam."""

    # OpenCode Go routes on a stable per-conversation session id
    # (https://opencode.ai/docs/go/#where-can-i-use-it). Other
    # OpenAI-compatible endpoints ignore the extra header.
    SESSION_HEADER = "x-opencode-session"

    def __init__(self, config: OpenAICompatConfig,
                 registry: CapabilityRegistry):
        self._config = config
        self._registry = registry
        self._cancelled = threading.Event()
        self._session_key = uuid.uuid4().hex

    @property
    def config(self) -> OpenAICompatConfig:
        return self._config

    def cancel(self) -> None:
        """Cooperative cancel: honored before dispatch. An in-flight
        HTTP call is still bounded by the configured timeout."""
        self._cancelled.set()

    def propose(self, context: ModelContext) -> ActionRequest:
        if self._cancelled.is_set():
            raise ProviderCancelled("cancelled before dispatch")
        body = build_request_body(
            self._config, context, skill_catalog(self._registry))
        session_id = context.session_id or self._session_key
        raw = self._post(body, session_id=session_id)
        try:
            data = json.loads(parse_response_body(raw))
        except ValueError as exc:
            raise StructuredProposalError(
                f"model did not return JSON: {exc}") from None
        return validate_proposal(data, self._registry)

    def _post(self, body: Dict[str, Any],
              session_id: str = "") -> Dict[str, Any]:
        payload = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self._config.endpoint + "/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json",
                     "User-Agent": USER_AGENT,
                     self.SESSION_HEADER: session_id
                     or self._session_key},
            method="POST",
        )
        if self._config.api_key:
            request.add_header(
                "Authorization", "Bearer " + self._config.api_key)
        try:
            with urllib.request.urlopen(
                    request,
                    timeout=self._config.timeout_seconds) as response:
                raw = response.read()
        except TimeoutError as exc:
            raise ProviderTimeout(
                f"provider call exceeded "
                f"{self._config.timeout_seconds}s") from exc
        except urllib.error.HTTPError as exc:
            raise ProviderError(
                f"provider HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, TimeoutError):
                raise ProviderTimeout(
                    f"provider call exceeded "
                    f"{self._config.timeout_seconds}s") from exc
            raise ProviderError(
                f"provider unreachable: {type(exc).__name__}") from None
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise ProviderError(
                f"provider returned non-JSON: {exc}") from None
        if not isinstance(parsed, dict):
            raise ProviderError("provider returned non-object JSON")
        return parsed


__all__ = [
    "ENDPOINT_ENV",
    "API_KEY_ENV",
    "MODEL_ENV",
    "DoneSignal",
    "OpenAICompatAdapter",
    "OpenAICompatConfig",
    "ProviderCancelled",
    "ProviderConfigError",
    "ProviderError",
    "ProviderTimeout",
    "StructuredProposalError",
    "build_request_body",
    "config_from_env",
    "parse_response_body",
    "provider_from_env",
    "skill_catalog",
    "validate_proposal",
]
