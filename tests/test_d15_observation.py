from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import dataclass

from raphael_ibm_bob.d14_state_codec import service_from_observation
from raphael_ibm_bob.d14_world_state import (
    ObservationUpdate,
    _ObservationKind,
    _observation_kind,
)
from raphael_ibm_bob.d15_observation import (
    ArtifactConfigurationMetadata,
    DnsMetadata,
    ObservationContext,
    ServiceBannerMetadata,
    SmbServiceMetadata,
    SshServiceMetadata,
    TlsMetadata,
    build_artifact_configuration,
    build_dns_metadata,
    build_service_banner,
    build_smb_service,
    build_ssh_service,
    build_tls_metadata,
)
from raphael_ibm_bob.observation_model import ObservationRecord


class D15ObservationTests(unittest.TestCase):
    @dataclass(frozen=True, slots=True)
    class _BrokerRuntime:
        session_id: str

    def _context(self, port: int | None = 443) -> ObservationContext:
        return ObservationContext.from_governed_runtime(
            capability_id="NETWORK_D15_METADATA",
            target_host="HOST.EXAMPLE",
            target_port=port,
            runtime_session=self._BrokerRuntime("broker-session-1"),
        )

    def _records(self) -> list[ObservationRecord]:
        context = self._context()
        return [
            build_ssh_service(
                context,
                SshServiceMetadata(
                    protocol_version="SSH-2.0",
                    version_banner_hash="banner-hash",
                    host_key_algorithms=("ssh-rsa", "ssh-ed25519"),
                ),
            ),
            build_smb_service(
                context,
                SmbServiceMetadata(
                    dialects=("SMB3", "SMB2"),
                    signing_status="SUPPORTED",
                    capability_flags=("DFS", "LARGE_MTU"),
                ),
            ),
            build_tls_metadata(
                context,
                TlsMetadata(
                    tls_version="TLSv1.3",
                    cipher_suite="TLS_AES_256_GCM_SHA384",
                    certificate_subject_hash="subject-hash",
                    certificate_issuer_hash="issuer-hash",
                    certificate_not_before="2025-01-01T00:00:00Z",
                    certificate_not_after="2026-01-01T00:00:00Z",
                    certificate_fingerprint="fingerprint",
                    verification_status="VERIFIED",
                ),
            ),
            build_dns_metadata(
                context,
                DnsMetadata(
                    transport="UDP",
                    response_code="NOERROR",
                    record_types=("AAAA", "A"),
                    answer_count=2,
                    ttl_min=60,
                    ttl_max=300,
                    dnssec_status="SECURE",
                ),
            ),
            build_service_banner(
                context,
                ServiceBannerMetadata(
                    protocol="HTTPS",
                    transport="TCP",
                    banner_hash="banner-hash",
                    version="2.4",
                ),
            ),
            build_artifact_configuration(
                self._context(None),
                ArtifactConfigurationMetadata(
                    artifact_type="service-config",
                    artifact_hash="artifact-hash",
                    format="ini",
                    size_bytes=128,
                    entry_count=4,
                    schema_version="1",
                ),
            ),
        ]

    def test_each_family_produces_an_observation_record(self) -> None:
        records = self._records()

        self.assertEqual(len(records), 6)
        self.assertTrue(all(isinstance(record, ObservationRecord) for record in records))
        self.assertTrue(all(record.provenance["session_id"] == "broker-session-1" for record in records))
        self.assertTrue(all("normalized" in record.provenance for record in records))

    def test_observation_family_derives_service_protocol(self) -> None:
        expected = {
            "ssh_service": "ssh",
            "smb_service": "smb",
            "tls_metadata": "tls",
            "dns_metadata": "dns",
            "service_banner": "https",
        }

        observed = {
            record.observation_type: service_from_observation(record).protocol
            for record in self._records()
            if record.observation_type in expected
        }

        self.assertEqual(observed, expected)

    def test_caller_supplied_session_id_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            ObservationContext(
                capability_id="NETWORK_D15_METADATA",
                target_host="HOST.EXAMPLE",
                target_port=443,
                session_id="forged-session",
            )

    def test_missing_authoritative_session_binding_fails_closed(self) -> None:
        context = ObservationContext(
            capability_id="NETWORK_D15_METADATA",
            target_host="HOST.EXAMPLE",
            target_port=443,
        )

        with self.assertRaisesRegex(
            ValueError,
            "authoritative session binding",
        ):
            build_ssh_service(context)

    def test_observation_types_are_family_specific_and_d14_unknown(self) -> None:
        expected = {
            "ssh_service",
            "smb_service",
            "tls_metadata",
            "dns_metadata",
            "service_banner",
            "artifact_configuration",
        }
        forbidden = {"network_response", "http_response", "http_get"}

        for record in self._records():
            self.assertIn(record.observation_type, expected)
            self.assertNotIn(record.observation_type, forbidden)
            self.assertIs(
                _observation_kind(ObservationUpdate(record, 1, "evidence-1")),
                _ObservationKind.UNKNOWN,
            )

    def test_metadata_is_canonical_and_sorted(self) -> None:
        context = self._context(22)
        first = build_ssh_service(
            context,
            SshServiceMetadata(
                host_key_algorithms=("ssh-rsa", "ssh-ed25519", "ssh-rsa"),
            ),
        )
        second = build_ssh_service(
            context,
            SshServiceMetadata(
                host_key_algorithms=("ssh-ed25519", "ssh-rsa"),
            ),
        )

        self.assertEqual(first.provenance["normalized"], second.provenance["normalized"])
        self.assertEqual(first.content_hash, second.content_hash)
        self.assertEqual(
            first.provenance["normalized"]["host_key_algorithms"],
            ["ssh-ed25519", "ssh-rsa"],
        )
        canonical = json.dumps(
            first.provenance["normalized"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        self.assertEqual(first.content_hash, hashlib.sha256(canonical.encode()).hexdigest())

    def test_metadata_and_strings_are_bounded_without_sensitive_fields(self) -> None:
        record = build_smb_service(
            self._context(445),
            SmbServiceMetadata(
                dialects=tuple(f"dialect-{index}" for index in range(100)),
                capability_flags=tuple(f"flag-{index}" for index in range(100)),
            ),
        )
        normalized = record.provenance["normalized"]

        self.assertLessEqual(len(normalized["dialects"]), 32)
        self.assertLessEqual(len(normalized["capability_flags"]), 32)
        encoded = json.dumps(record.to_evidence_dict(), sort_keys=True)
        for forbidden in (
            "credential",
            "password",
            "private_key",
            "raw_banner",
            "share_name",
            "username",
            "dns_answer",
            "file_contents",
        ):
            self.assertNotIn(forbidden, encoded.lower())

        self.assertNotIn("SSH-2.0-raw-banner", encoded)


if __name__ == "__main__":
    unittest.main()
