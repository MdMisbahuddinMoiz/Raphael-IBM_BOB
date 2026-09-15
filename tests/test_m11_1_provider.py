"""tests.test_m11_1_provider — live-provider adapter unit tests.

The HTTP boundary is exercised for real against an in-process stub
server (canned chat-completions responses, error modes, delays).
RAPHAEL core is not involved here; integration lives in
tests.test_m11_4_integration.
"""
from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from raphael_ibm_bob import Capability
from raphael_ibm_bob.harness.model import ModelContext
from raphael_ibm_bob.harness.providers.openai_compat import (
    DoneSignal,
    OpenAICompatConfig,
    OpenAICompatAdapter,
    ProviderCancelled,
    ProviderConfigError,
    ProviderError,
    ProviderTimeout,
    StructuredProposalError,
    build_request_body,
    config_from_env,
    parse_response_body,
    provider_from_env,
    skill_catalog,
    validate_proposal,
)
from raphael_ibm_bob.skills import (
    CapabilityRegistry,
    SkillDefinition,
    default_registry,
)


def _skill() -> SkillDefinition:
    return SkillDefinition(
        id="read-file", name="Read file", version="1.0",
        description="Read a file.", capability=Capability.READ,
        target_schema="relative path",
        purpose_template="read:{target}",
        success_markers=("OK",))


def _registry() -> CapabilityRegistry:
    reg = default_registry()
    reg.register_skill(_skill())
    return reg


class StubServer:
    """In-process chat-completions stub with programmable behavior."""

    def __init__(self, testcase: unittest.TestCase):
        self.mode = "ok"
        self.payload = {"intent": "act", "skill": "read-file",
                        "target": "src/a.txt", "purpose": "inspect"}
        self.delay = 0.0
        self.hits = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                outer.hits += 1
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                if outer.delay:
                    import time
                    time.sleep(outer.delay)
                if outer.mode == "http500":
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b"boom")
                    return
                if outer.mode == "garbage":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b"not-json{{{")
                    return
                if outer.mode == "empty-choices":
                    body = {"choices": []}
                elif outer.mode == "empty-content":
                    body = {"choices": [{"message": {"content": "  "}}]}
                else:
                    body = {"choices": [{"message": {
                        "content": json.dumps(outer.payload)}}]}
                raw = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        testcase.addCleanup(self._server.server_close)
        self.thread = threading.Thread(
            target=self._server.serve_forever, daemon=True)
        self.thread.start()
        testcase.addCleanup(self._server.shutdown)

    @property
    def url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def config(self, **overrides) -> OpenAICompatConfig:
        params = dict(endpoint=self.url, model="stub-model",
                      timeout_seconds=10.0)
        params.update(overrides)
        return OpenAICompatConfig(**params)


def _context() -> ModelContext:
    from raphael_ibm_bob import Mission
    return ModelContext(
        mission=Mission(mission_id="M-p", description="x", scope="src/",
                        criteria=["x"],
                        problem={"symptom_target": "src/a.txt"}))


class RequestFormatting(unittest.TestCase):
    def test_body_shape(self):
        config = OpenAICompatConfig(endpoint="http://x", model="m")
        body = build_request_body(config, _context(),
                                  skill_catalog(_registry()))
        self.assertEqual(body["model"], "m")
        self.assertEqual(body["response_format"],
                         {"type": "json_object"})
        self.assertEqual(body["temperature"], 0)
        roles = [m["role"] for m in body["messages"]]
        self.assertEqual(roles, ["system", "user"])
        user = json.loads(body["messages"][1]["content"])
        self.assertEqual(user["mission"]["mission_id"], "M-p")
        self.assertTrue(any(s["skill"] == "read-file"
                            for s in user["available_skills"]))

    def test_catalog_comes_from_registry(self):
        reg = default_registry()
        self.assertFalse(any(s["skill"] == "read-file"
                             for s in skill_catalog(reg)))
        reg.register_skill(_skill())
        self.assertTrue(any(s["skill"] == "read-file"
                            for s in skill_catalog(reg)))


class ConfigValidation(unittest.TestCase):
    def test_bad_endpoint_rejected(self):
        with self.assertRaises(ProviderConfigError):
            OpenAICompatConfig(endpoint="ftp://x", model="m")

    def test_empty_model_rejected(self):
        with self.assertRaises(ProviderConfigError):
            OpenAICompatConfig(endpoint="http://x", model="")

    def test_bad_timeout_rejected(self):
        with self.assertRaises(ProviderConfigError):
            OpenAICompatConfig(endpoint="http://x", model="m",
                               timeout_seconds=0)

    def test_from_env_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ProviderConfigError) as ctx:
                config_from_env()
        self.assertIn("RAPHAEL_MODEL_ENDPOINT", str(ctx.exception))

    def test_from_env_ok_and_redacted(self):
        env = {"RAPHAEL_MODEL_ENDPOINT": "http://x/v1",
               "RAPHAEL_MODEL_NAME": "m",
               "RAPHAEL_MODEL_API_KEY": "super-secret-value"}
        with patch.dict("os.environ", env, clear=True):
            config = config_from_env()
        self.assertEqual(config.endpoint, "http://x/v1")
        redacted = config.redacted()
        self.assertEqual(redacted["api_key"], "set")
        self.assertNotIn("super-secret-value", json.dumps(redacted))

    def test_unknown_provider_rejected(self):
        with self.assertRaises(ProviderConfigError):
            provider_from_env("does-not-exist", _registry())


class ResponseParsing(unittest.TestCase):
    def test_extracts_content(self):
        body = {"choices": [{"message": {"content": '{"a": 1}'}}]}
        self.assertEqual(parse_response_body(body), '{"a": 1}')

    def test_missing_choices(self):
        with self.assertRaises(ProviderError):
            parse_response_body({"nope": []})

    def test_empty_content(self):
        with self.assertRaises(StructuredProposalError):
            parse_response_body({"choices": [{"message": {
                "content": "   "}}]})


class ProposalValidation(unittest.TestCase):
    def test_valid_proposal_builds_request(self):
        req = validate_proposal(
            {"intent": "act", "skill": "read-file",
             "target": "src/a.txt", "purpose": "look"},
            _registry())
        self.assertEqual(req.capability, Capability.READ)
        self.assertEqual(req.target, "src/a.txt")
        self.assertEqual(req.purpose, "look")
        self.assertEqual(req.requester, "skill:read-file")

    def test_unknown_skill_rejected(self):
        with self.assertRaises(StructuredProposalError):
            validate_proposal(
                {"intent": "act", "skill": "nope",
                 "target": "t", "purpose": "p"}, _registry())

    def test_missing_fields_rejected(self):
        base = {"intent": "act", "skill": "read-file",
                "target": "t", "purpose": "p"}
        for key in ("skill", "target", "purpose"):
            broken = dict(base)
            broken[key] = ""
            with self.assertRaises(StructuredProposalError, msg=key):
                validate_proposal(broken, _registry())

    def test_bad_intent_rejected(self):
        with self.assertRaises(StructuredProposalError):
            validate_proposal({"intent": "launch"}, _registry())

    def test_non_object_rejected(self):
        with self.assertRaises(StructuredProposalError):
            validate_proposal(["act"], _registry())

    def test_done_signal(self):
        with self.assertRaises(DoneSignal):
            validate_proposal({"intent": "done"}, _registry())


class ProviderFailures(unittest.TestCase):
    def test_http_500(self):
        stub = StubServer(self)
        stub.mode = "http500"
        adapter = OpenAICompatAdapter(stub.config(), _registry())
        with self.assertRaises(ProviderError) as ctx:
            adapter.propose(_context())
        self.assertIn("500", str(ctx.exception))

    def test_connection_refused(self):
        config = OpenAICompatConfig(
            endpoint="http://127.0.0.1:9", model="m",
            timeout_seconds=2.0)
        adapter = OpenAICompatAdapter(config, _registry())
        with self.assertRaises(ProviderError):
            adapter.propose(_context())

    def test_timeout(self):
        stub = StubServer(self)
        stub.delay = 5.0
        adapter = OpenAICompatAdapter(
            stub.config(timeout_seconds=1.0), _registry())
        with self.assertRaises(ProviderTimeout):
            adapter.propose(_context())

    def test_garbage_response(self):
        stub = StubServer(self)
        stub.mode = "garbage"
        adapter = OpenAICompatAdapter(stub.config(), _registry())
        with self.assertRaises(ProviderError):
            adapter.propose(_context())

    def test_empty_choices(self):
        stub = StubServer(self)
        stub.mode = "empty-choices"
        adapter = OpenAICompatAdapter(stub.config(), _registry())
        with self.assertRaises(ProviderError):
            adapter.propose(_context())

    def test_cancel_before_dispatch(self):
        stub = StubServer(self)
        adapter = OpenAICompatAdapter(stub.config(), _registry())
        adapter.cancel()
        with self.assertRaises(ProviderCancelled):
            adapter.propose(_context())
        self.assertEqual(stub.hits, 0)


class LivePropose(unittest.TestCase):
    def test_ok_proposal(self):
        stub = StubServer(self)
        adapter = OpenAICompatAdapter(stub.config(), _registry())
        req = adapter.propose(_context())
        self.assertEqual(req.capability, Capability.READ)
        self.assertEqual(req.target, "src/a.txt")
        self.assertEqual(stub.hits, 1)

    def test_secret_never_leaks(self):
        stub = StubServer(self)
        adapter = OpenAICompatAdapter(
            stub.config(api_key="super-secret-value"), _registry())
        req = adapter.propose(_context())
        blob = json.dumps({
            "capability": req.capability.value,
            "target": req.target,
            "purpose": req.purpose,
            "requester": req.requester,
        })
        self.assertNotIn("super-secret-value", blob)
        try:
            stub.mode = "http500"
            adapter.propose(_context())
        except ProviderError as exc:
            self.assertNotIn("super-secret-value", str(exc))


class WriteContentRules(unittest.TestCase):
    def _wregistry(self):
        from raphael_ibm_bob.skills import SkillDefinition
        reg = _registry()
        reg.register_skill(SkillDefinition(
            id="write-file", name="Write file", version="1.0",
            description="Write a file.", capability=Capability.WRITE,
            target_schema="relative path",
            purpose_template="write:{target}"))
        return reg

    def test_write_with_content(self):
        req = validate_proposal(
            {"intent": "act", "skill": "write-file",
             "target": "src/a.txt", "purpose": "fix it",
             "content": "OK\n"},
            self._wregistry())
        self.assertEqual(req.capability, Capability.WRITE)
        self.assertTrue(req.purpose.startswith("content="))
        self.assertIn("OK", req.purpose)

    def test_write_without_content_rejected(self):
        with self.assertRaises(StructuredProposalError):
            validate_proposal(
                {"intent": "act", "skill": "write-file",
                 "target": "src/a.txt", "purpose": "fix it"},
                self._wregistry())

    def test_content_on_read_rejected(self):
        with self.assertRaises(StructuredProposalError):
            validate_proposal(
                {"intent": "act", "skill": "read-file",
                 "target": "src/a.txt", "purpose": "look",
                 "content": "sneaky"},
                _registry())

    def test_oversize_content_rejected(self):
        with self.assertRaises(StructuredProposalError):
            validate_proposal(
                {"intent": "act", "skill": "write-file",
                 "target": "src/a.txt", "purpose": "fix it",
                 "content": "x" * 9000},
                self._wregistry())


class ExtraBodyConfig(unittest.TestCase):
    def test_extra_body_merged(self):
        from raphael_ibm_bob.harness.model import ModelContext
        from raphael_ibm_bob import Mission
        config = OpenAICompatConfig(
            endpoint="http://x", model="m",
            extra_body={"reasoning_effort": "none"})
        ctx = ModelContext(
            mission=Mission(mission_id="M", description="x",
                            scope="src/", criteria=["x"]))
        body = build_request_body(config, ctx, [])
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertEqual(body["model"], "m")
        self.assertIn("messages", body)

    def test_extra_body_cannot_override_core_fields(self):
        from raphael_ibm_bob.harness.model import ModelContext
        from raphael_ibm_bob import Mission
        config = OpenAICompatConfig(
            endpoint="http://x", model="m",
            extra_body={"model": "evil",
                        "reasoning_effort": "none"})
        ctx = ModelContext(
            mission=Mission(mission_id="M", description="x",
                            scope="src/", criteria=["x"]))
        body = build_request_body(config, ctx, [])
        self.assertEqual(body["model"], "m")
        self.assertEqual(body["reasoning_effort"], "none")

    def test_extra_body_from_env(self):
        from unittest.mock import patch
        from raphael_ibm_bob.harness.providers.openai_compat import (
            config_from_env,
        )
        env = {"RAPHAEL_MODEL_ENDPOINT": "http://x/v1",
               "RAPHAEL_MODEL_NAME": "m",
               "RAPHAEL_MODEL_EXTRA_BODY":
                   '{"reasoning_effort": "none"}'}
        with patch.dict("os.environ", env, clear=True):
            config = config_from_env()
        self.assertEqual(config.extra_body,
                         {"reasoning_effort": "none"})

    def test_extra_body_bad_json_rejected(self):
        from unittest.mock import patch
        from raphael_ibm_bob.harness.providers.openai_compat import (
            config_from_env,
        )
        env = {"RAPHAEL_MODEL_ENDPOINT": "http://x/v1",
               "RAPHAEL_MODEL_NAME": "m",
               "RAPHAEL_MODEL_EXTRA_BODY": "not-json"}
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaises(ProviderConfigError):
                config_from_env()


class MaxTokensConfig(unittest.TestCase):
    def test_default_512(self):
        from unittest.mock import patch
        from raphael_ibm_bob.harness.providers.openai_compat import (
            config_from_env,
        )
        env = {"RAPHAEL_MODEL_ENDPOINT": "http://x/v1",
               "RAPHAEL_MODEL_NAME": "m"}
        with patch.dict("os.environ", env, clear=True):
            self.assertEqual(config_from_env().max_tokens, 512)

    def test_env_override(self):
        from unittest.mock import patch
        from raphael_ibm_bob.harness.providers.openai_compat import (
            config_from_env,
        )
        env = {"RAPHAEL_MODEL_ENDPOINT": "http://x/v1",
               "RAPHAEL_MODEL_NAME": "m",
               "RAPHAEL_MODEL_MAX_TOKENS": "2048"}
        with patch.dict("os.environ", env, clear=True):
            self.assertEqual(config_from_env().max_tokens, 2048)

    def test_bad_values_rejected(self):
        from unittest.mock import patch
        from raphael_ibm_bob.harness.providers.openai_compat import (
            config_from_env,
        )
        for bad in ("many", "0", "-5"):
            env = {"RAPHAEL_MODEL_ENDPOINT": "http://x/v1",
                   "RAPHAEL_MODEL_NAME": "m",
                   "RAPHAEL_MODEL_MAX_TOKENS": bad}
            with patch.dict("os.environ", env, clear=True):
                with self.assertRaises(ProviderConfigError, msg=bad):
                    config_from_env()

    def test_body_carries_max_tokens(self):
        from raphael_ibm_bob.harness.model import ModelContext
        from raphael_ibm_bob import Mission
        config = OpenAICompatConfig(
            endpoint="http://x", model="m", max_tokens=2048)
        ctx = ModelContext(
            mission=Mission(mission_id="M", description="x",
                            scope="src/", criteria=["x"]))
        body = build_request_body(config, ctx, [])
        self.assertEqual(body["max_tokens"], 2048)


class LenientIntentGrammar(unittest.TestCase):
    def test_bare_skill_id_accepted(self):
        req = validate_proposal(
            {"intent": "read-file", "skill": "read-file",
             "target": "src/a.txt", "purpose": "look"},
            _registry())
        self.assertEqual(req.capability, Capability.READ)
        self.assertEqual(req.target, "src/a.txt")

    def test_bare_skill_id_without_skill_field(self):
        req = validate_proposal(
            {"intent": "read-file",
             "target": "src/a.txt", "purpose": "look"},
            _registry())
        self.assertEqual(req.requester, "skill:read-file")

    def test_conflicting_skill_rejected(self):
        with self.assertRaises(StructuredProposalError):
            validate_proposal(
                {"intent": "read-file", "skill": "run-test",
                 "target": "src/a.txt", "purpose": "look"},
                _registry())

    def test_unknown_intent_string_rejected(self):
        with self.assertRaises(StructuredProposalError):
            validate_proposal(
                {"intent": "launch-missiles", "skill": "read-file",
                 "target": "src/a.txt", "purpose": "look"},
                _registry())

    def test_non_string_intent_rejected(self):
        with self.assertRaises(StructuredProposalError):
            validate_proposal(
                {"intent": 42, "skill": "read-file",
                 "target": "src/a.txt", "purpose": "look"},
                _registry())


class CapabilityIntentGrammar(unittest.TestCase):
    def test_capability_intent_with_agreeing_skill(self):
        req = validate_proposal(
            {"intent": "read", "skill": "read-file",
             "target": "src/a.txt", "purpose": "look"},
            _registry())
        self.assertEqual(req.capability, Capability.READ)
        self.assertEqual(req.target, "src/a.txt")

    def test_capability_intent_without_skill_rejected(self):
        with self.assertRaises(StructuredProposalError):
            validate_proposal(
                {"intent": "read",
                 "target": "src/a.txt", "purpose": "look"},
                _registry())

    def test_capability_intent_disagreeing_skill_rejected(self):
        with self.assertRaises(StructuredProposalError):
            validate_proposal(
                {"intent": "write", "skill": "read-file",
                 "target": "src/a.txt", "purpose": "look"},
                _registry())

    def test_unknown_word_rejected(self):
        with self.assertRaises(StructuredProposalError):
            validate_proposal(
                {"intent": "examine", "skill": "read-file",
                 "target": "src/a.txt", "purpose": "look"},
                _registry())


class SystemPromptContract(unittest.TestCase):
    def test_prompt_bans_repeats(self):
        from raphael_ibm_bob.harness.providers.openai_compat import (
            _SYSTEM_PROMPT,
        )
        self.assertIn("Do not repeat", _SYSTEM_PROMPT)
        self.assertIn("recent turns", _SYSTEM_PROMPT)


class TemperatureConfig(unittest.TestCase):
    def _env(self, **over):
        env = {"RAPHAEL_MODEL_ENDPOINT": "http://x/v1",
               "RAPHAEL_MODEL_NAME": "m"}
        env.update(over)
        return env

    def test_default_zero(self):
        from unittest.mock import patch
        from raphael_ibm_bob.harness.providers.openai_compat import (
            config_from_env,
        )
        with patch.dict("os.environ", self._env(), clear=True):
            self.assertEqual(config_from_env().temperature, 0.0)

    def test_env_override_and_body(self):
        from unittest.mock import patch
        from raphael_ibm_bob.harness.model import ModelContext
        from raphael_ibm_bob import Mission
        from raphael_ibm_bob.harness.providers.openai_compat import (
            build_request_body,
            config_from_env,
        )
        env = self._env(RAPHAEL_MODEL_TEMPERATURE="0.4")
        with patch.dict("os.environ", env, clear=True):
            config = config_from_env()
        self.assertEqual(config.temperature, 0.4)
        ctx = ModelContext(
            mission=Mission(mission_id="M", description="x",
                            scope="src/", criteria=["x"]))
        body = build_request_body(config, ctx, [])
        self.assertEqual(body["temperature"], 0.4)

    def test_bad_values_rejected(self):
        from unittest.mock import patch
        from raphael_ibm_bob.harness.providers.openai_compat import (
            config_from_env,
        )
        for bad in ("warm", "-0.5", "2.5"):
            env = self._env(RAPHAEL_MODEL_TEMPERATURE=bad)
            with patch.dict("os.environ", env, clear=True):
                with self.assertRaises(ProviderConfigError, msg=bad):
                    config_from_env()


if __name__ == "__main__":
    unittest.main()
