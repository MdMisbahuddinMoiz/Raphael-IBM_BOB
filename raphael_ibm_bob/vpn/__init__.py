"""raphael_ibm_bob.vpn — HTB-compatible OpenVPN connectivity (D7).

A minimal, controlled VPN lifecycle for the existing BOB operator UI:
the operator supplies an authorized ``.ovpn`` profile, the manager starts
OpenVPN with an argument array, verifies the tunnel, exposes a safe
status view, and terminates the process deterministically.

This package performs NO target discovery, scanning, or exploitation.
"""
from raphael_ibm_bob.vpn.manager import (
    DEFAULT_OPENVPN_BIN,
    DEFAULT_STATE_ROOT,
    OPENVPN_BIN_ENV,
    VPNConflict,
    VPNError,
    VPNExecutableNotFound,
    VPNManager,
    VPNProfileError,
    get_vpn_manager,
    set_vpn_manager,
)
from raphael_ibm_bob.vpn.profile import (
    MAX_PROFILE_BYTES,
    ProfileError,
    validate_profile,
)

__all__ = [
    "DEFAULT_OPENVPN_BIN",
    "DEFAULT_STATE_ROOT",
    "MAX_PROFILE_BYTES",
    "OPENVPN_BIN_ENV",
    "ProfileError",
    "VPNConflict",
    "VPNError",
    "VPNExecutableNotFound",
    "VPNManager",
    "VPNProfileError",
    "get_vpn_manager",
    "set_vpn_manager",
    "validate_profile",
]
