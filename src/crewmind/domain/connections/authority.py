"""The install's own certificate authority for the egress proxy (CON-6, ADR-0010).

Validity is measured on the wall clock, never the platform's clock: real TLS clients check
certificates against real time.

The proxy opens a connection to a site that has a secret sent for the run with a short-lived
certificate for that site, signed by this authority, which every sandbox trusts. The
authority's key is a secret: stored encrypted, held in this process only, never in a
sandbox. Leaf certificates are made on demand and kept in memory until they expire.
"""

from __future__ import annotations

import ssl
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

AUTHORITY_LIFE = timedelta(days=3650)
"""CON-6: the authority is valid for ten years; leaf certificates for `proxy.certificate_life`."""
BACKDATE = timedelta(minutes=5)
"""Leaf certificates start a little in the past, so a sandbox clock slightly behind still
accepts them."""


@dataclass(frozen=True)
class Authority:
    key_pem: bytes
    certificate_pem: bytes

    @classmethod
    def create(cls, name: str) -> Authority:
        now = datetime.now(UTC)  # checked by real TLS clients against real time
        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - BACKDATE)
            .not_valid_after(now + AUTHORITY_LIFE)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_cert_sign=True,
                    crl_sign=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
            .sign(key, hashes.SHA256())
        )
        return cls(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
            certificate.public_bytes(serialization.Encoding.PEM),
        )

    def leaf(self, host: str, life: timedelta) -> tuple[bytes, bytes]:
        """A certificate for one site, and its key, both PEM."""
        now = datetime.now(UTC)
        authority_key = serialization.load_pem_private_key(self.key_pem, password=None)
        assert isinstance(authority_key, ec.EllipticCurvePrivateKey)
        authority = x509.load_pem_x509_certificate(self.certificate_pem)
        key = ec.generate_private_key(ec.SECP256R1())
        certificate = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)]))
            .issuer_name(authority.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - BACKDATE)
            .not_valid_after(now + life)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(authority_key.public_key()),
                critical=False,
            )
            .sign(authority_key, hashes.SHA256())
        )
        return (
            certificate.public_bytes(serialization.Encoding.PEM),
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
        )


@dataclass
class LeafCache:
    """Server TLS contexts per site, made on demand and dropped once expired. In memory
    only: a leaf key is never written anywhere but a private temporary file that is removed
    as soon as the context has loaded it."""

    authority: Authority
    life: timedelta
    _contexts: dict[str, tuple[ssl.SSLContext, datetime]] = field(
        default_factory=dict[str, tuple[ssl.SSLContext, datetime]]
    )

    def context(self, host: str) -> ssl.SSLContext:
        now = datetime.now(UTC)
        found = self._contexts.get(host)
        if found is not None and found[1] > now:
            return found[0]
        certificate, key = self.authority.leaf(host, self.life)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.set_alpn_protocols(["http/1.1"])

        def same_site(_: object, name: str | None, __: object) -> int | None:
            # CON-6: the TLS server name must be the site this certificate is for.
            return None if name == host else ssl.ALERT_DESCRIPTION_UNRECOGNIZED_NAME

        context.sni_callback = same_site  # pyright: ignore[reportAttributeAccessIssue]
        with tempfile.TemporaryDirectory() as directory:
            pem = Path(directory) / "leaf.pem"
            pem.touch(mode=0o600)
            pem.write_bytes(certificate + key)
            context.load_cert_chain(pem)
        # Renewed a little before it expires, so a connection never starts on a dying one.
        self._contexts[host] = (context, now + self.life / 2)
        return context
