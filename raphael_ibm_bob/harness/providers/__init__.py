"""raphael_ibm_bob.harness.providers — model provider adapters.

Only the boundary the Harness needs: env-driven configuration plus
ONE real provider (OpenAI-compatible HTTP, stdlib `urllib` — no new
dependencies). No routing, marketplace, fallback orchestration, or
multi-provider platform.

Credential discipline (enforced by tests):
- Keys come ONLY from the environment, never code or tests.
- The key is sent as an HTTP header and NEVER appears in
  exceptions, logs, evidence payloads, or returned objects.
- `.env` files are never read by this module; no secret is written
  anywhere. Missing configuration fails loudly before any request.

If no endpoint/credentials exist in an environment, nothing here can
run live — that is reported as BLOCKED, never faked.
"""
from raphael_ibm_bob.harness.providers.openai_compat import (
    DoneSignal,
    OpenAICompatAdapter,
    OpenAICompatConfig,
    ProviderCancelled,
    ProviderConfigError,
    ProviderError,
    ProviderTimeout,
    StructuredProposalError,
    provider_from_env,
)

__all__ = [
    "DoneSignal",
    "OpenAICompatAdapter",
    "OpenAICompatConfig",
    "ProviderCancelled",
    "ProviderConfigError",
    "ProviderError",
    "ProviderTimeout",
    "StructuredProposalError",
    "provider_from_env",
]
