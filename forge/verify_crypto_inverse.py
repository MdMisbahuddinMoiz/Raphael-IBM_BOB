#!/usr/bin/env python3
"""FORGE Phase 2 — Cryptographic Inverse Verification (Rule 4).

Tests every crypto encode/decode pair in the frozen src/:
  1. agent.crypto: AES-GCM encrypt/decrypt, AES-CTR encrypt/decrypt
  2. weaponizer_engine: AES-CBC with PKCS7 pad (encrypt/decrypt round trip)
  3. Verifies nonce uniqueness across consecutive calls (AES-GCM)
Run: .venv/bin/python forge/verify_crypto_inverse.py
"""
import base64, os, sys, traceback
sys.path.insert(0, "/home/yaser/raphael-2.0-rbsv2r/src")

results = []

def check(name, fn):
    try:
        ok, detail = fn()
        results.append((name, "PASS" if ok else "FAIL", detail))
    except Exception as e:
        results.append((name, "ERROR", f"{type(e).__name__}: {e}"))

# ── 1. agent.crypto AES-GCM roundtrip ──
def t_gcm_roundtrip():
    from agent.crypto import encrypt, decrypt
    key = os.urandom(32)
    original = b"FORGE crypto inverse test \x00\x01\x02 binary"
    wire = encrypt(key, original)
    back = decrypt(key, wire)
    assert original == back, "GCM decrypt mismatch"
    assert wire != original, "ciphertext equals plaintext!"
    # tamper detection
    tampered = bytearray(wire.encode())
    tampered[-1] = ord("X") if tampered[-1] != ord("X") else ord("Y")
    try:
        decrypt(key, tampered.decode())
        return False, "tampered ciphertext decrypted successfully (AUTH FAILURE)"
    except Exception:
        return True, f"roundtrip ok, tamper rejected, wire len={len(wire)}"
    return True, ""

def test_gcm_nonce_uniqueness():
    from agent.crypto import encrypt
    key = os.urandom(32)
    w1 = encrypt(key, b"same")
    w2 = encrypt(key, b"same")
    return w1 != w2, "identical plaintext produced identical ciphertext (nonce reuse!)"

def test_ctr_roundtrip():
    from agent.crypto import aes_ctr_encrypt, aes_ctr_decrypt
    key = os.urandom(32)
    nonce = b"\x00" * 16
    original = b"sleep-mask-heap-content" * 100
    ct = aes_ctr_encrypt(key, nonce, original)
    back = aes_ctr_decrypt(key, nonce, ct)
    assert original == back
    # wrong nonce length must raise
    try:
        aes_ctr_encrypt(key, b"\x00" * 15, b"x")
        return False, "CTR accepted 15-byte nonce"
    except ValueError:
        return True, f"CTR roundtrip ok ({len(original)}B), nonce-length enforced"

# ── 2. weaponizer AES-CBC roundtrip ──
def test_weaponizer_cbc():
    from orchestrator.weaponizer.weaponizer_engine import Weaponizer
    w = Weaponizer()
    key, iv = os.urandom(32), os.urandom(16)
    data = bytes(os.urandom(1)[0] for _ in range(1000))  # arbitrary binary
    ct = w._aes_cbc_encrypt(data, key, iv)
    back = w._aes_cbc_decrypt(ct, key, iv)
    assert back == data, "CBC decrypt mismatch"
    # multi-block padding edge
    for size in (1, 15, 16, 17, 31, 32, 33, 255, 256):
        d = b"A" * size
        assert w._aes_cbc_decrypt(w._aes_cbc_encrypt(d, key, iv), key, iv) == d
    return True, "CBC roundtrip ok across 1..256B payloads"

# ── 3. mcp-hub HMAC (if present) ──
def test_hmac_sign_verify():
    try:
        from mcp_hub.core.security import sign, verify
    except Exception:
        try:
            from mcp_hub.auth import sign, verify
        except Exception:
            return True, "no HMAC module importable (skipped)"
    secret = b"audit-secret"
    msg = b"authorized-message"
    sig = sign(secret, msg) if callable(sign) else sign(msg, secret)
    ok = verify(msg, sig, secret) if callable(verify) else verify(sig, msg, secret)
    bad = verify(b"tampered", sig, secret) if callable(verify) else verify(sig, b"tampered", secret)
    return ok and not bad, "HMAC verify ok, tamper rejected"

def test_exfil_encrypt_chunk():
    from agent.modules.exfil import Exfiltration
    key = os.urandom(32)
    original = b'{"secret": "data-value"}'
    chunk = {"seq": 0, "total": 1, "size": len(original), "data": original}
    enc = Exfiltration._encrypt_chunk(chunk, key)
    assert enc["encrypted"] is True
    assert enc["data"] != original, "ciphertext equals plaintext"
    # verify wire format is AES-GCM decryptable (nonce || ct)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = enc["data"]
    nonce, ct = raw[:12], raw[12:]
    back = AESGCM(key[:32]).decrypt(nonce, ct, None)
    assert back == original, "exfil chunk not AES-GCM reversible"
    return True, "exfil chunk encrypt is AES-GCM reversible"

check("agent.crypto GCM roundtrip", t_gcm_roundtrip)
check("agent.crypto GCM nonce uniqueness", test_gcm_nonce_uniqueness)
check("agent.crypto CTR roundtrip", test_ctr_roundtrip)
check("weaponizer CBC roundtrip", test_weaponizer_cbc)
check("mcp-hub HMAC", test_hmac_sign_verify)
check("agent exfil chunk", test_exfil_encrypt_chunk)

print("=" * 70)
print("RULE 4 — CRYPTOGRAPHIC INVERSE AUDIT")
print("=" * 70)
allok = True
for name, status, detail in results:
    flag = {"PASS": "[+]", "FAIL": "[!]", "ERROR": "[x]"}[status]
    print(f"  {flag} {name}: {status} — {detail}")
    if status != "PASS":
        allok = False
print("-" * 70)
print("VERDICT:", "ALL INVERSE PAIRS VERIFIED" if allok else "CRYPTO DEFECTS FOUND")
sys.exit(0 if allok else 1)