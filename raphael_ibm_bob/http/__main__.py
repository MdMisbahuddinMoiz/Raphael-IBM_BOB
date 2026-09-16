"""`python3 -m raphael_ibm_bob.http` entrypoint.

Delegates to the EXISTING HTTP application entrypoint
(`raphael_ibm_bob.http.app.main`) — it does not duplicate any server
logic, add a second server, change routes, or add dependencies. This
only makes the documented module invocation work.
"""
from __future__ import annotations

import sys

from raphael_ibm_bob.http.app import main

if __name__ == "__main__":
    sys.exit(main())
