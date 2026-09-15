"""raphael_ibm_bob.http.routes — HTTP route handlers.

Each handler takes `(request, path_params, config)` and returns a JSON
body (or an explicit `(status, body)` tuple). Handlers call the public
Harness API (`raphael_ibm_bob.harness.api`) and read-only declarations;
they never call execution, Broker, Policy, or QualityGate directly.
"""
