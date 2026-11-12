"""Explicit CA/leaf preparation and read-only inspection; never replace a broken CA silently.

Each private identity and each leaf key/certificate pair is replaced as ONE file.
The public profile has stable UUIDs derived from the CA, independent of leaf renewal.
"""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import plistlib
import tempfile
import uuid

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from ios_server.runtime import private_path

HELLO_HOST = 'v900-lapis.gumi.sg'
ROOT_NAME = 'Exvius Offline iOS Root'
DOMAINS = ('gumi.sg', 'exvius.com')
SANS = (HELLO_HOST, 'gumi.sg', '*.gumi.sg', 'exvius.com', '*.exvius.com', '*.notice.exvius.com')
_PEM = serialization.Encoding.PEM


def _now():
    return datetime.now(timezone.utc)


def _atomic(path, data, mode=0o600):
    """Private staging from creation, atomic replacement, and no leftover partial files."""
    if path.exists() and path.read_bytes() == data:
        path.chmod(mode)
        return
    descriptor, name = tempfile.mkstemp(prefix='.prepare-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class CertificateStore:
    def __init__(self, root):
        self.root = Path(root).resolve()

    @property
    def folder(self):
        return private_path(self.root, 'certs')

    def path(self, name):
        return private_path(self.root, 'certs/' + name)

    @property
    def identity(self):
        return self.path('identity.json')

    @property
    def leaf(self):
        return self.path('leaf.pem')

    @property
    def profile(self):
        return self.path('exvius-offline.mobileconfig')

    def _identity(self, now):
        if self.identity.exists():
            try:
                raw = json.loads(self.identity.read_bytes())
                cert = x509.load_pem_x509_certificate(raw['certificate'].encode())
                key = serialization.load_pem_private_key(raw['private_key'].encode(), None)
                if key.public_key().public_numbers() != cert.public_key().public_numbers():
                    raise ValueError('CA certificate and key do not match')
                if not cert.not_valid_before_utc <= now < cert.not_valid_after_utc - timedelta(days=30):
                    raise ValueError('CA expired or not valid now; explicit replacement and phone re-enrollment are required')
                self.identity.chmod(0o600)
                return key, cert
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f'Cannot use the existing iOS CA; it was preserved: {exc}') from exc
        # Do not replace a previously trusted public CA if its private identity was lost.
        if any(self.path(name).exists() for name in ('ca.pem', 'ca.crt', 'exvius-offline.mobileconfig', 'leaf.pem')):
            raise ValueError('The iOS private CA identity is missing; existing certificates were preserved.')
        key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
        name = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Exvius Offline'),
                          x509.NameAttribute(NameOID.COMMON_NAME, ROOT_NAME)])
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
                .not_valid_after(now + timedelta(days=3650))
                .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
                .add_extension(x509.NameConstraints([x509.DNSName(domain) for domain in DOMAINS], None), critical=True)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
                .sign(key, hashes.SHA256()))
        raw = {'certificate': cert.public_bytes(_PEM).decode(), 'private_key': key.private_bytes(
            _PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()}
        _atomic(self.identity, json.dumps(raw).encode())
        return key, cert

    def _leaf(self, now, ca_key, ca_cert):
        if self.leaf.exists():
            try:
                cert = x509.load_pem_x509_certificate(self.leaf.read_bytes())
                cert.verify_directly_issued_by(ca_cert)
                if cert.not_valid_before_utc <= now < cert.not_valid_after_utc - timedelta(days=30):
                    self.leaf.chmod(0o600)
                    return False
            except (ValueError, TypeError, InvalidSignature):
                raise ValueError('The iOS leaf certificate is invalid; run setup after inspecting the existing files.') from None
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cert = (x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HELLO_HOST)]))
                .issuer_name(ca_cert.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=397))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.KeyUsage(True, False, True, False, False, False, False, False, False), critical=True)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(host) for host in SANS]), critical=False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
                .sign(ca_key, hashes.SHA256()))
        _atomic(self.leaf, cert.public_bytes(_PEM) + key.private_bytes(
            _PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        return True

    def prepare(self, *, now=None):
        moment = now or _now()
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.folder.chmod(0o700)
        key, ca = self._identity(moment)
        renewed = self._leaf(moment, key, ca)
        der = ca.public_bytes(serialization.Encoding.DER)
        _atomic(self.path('ca.pem'), ca.public_bytes(_PEM), 0o644)
        _atomic(self.path('ca.crt'), der, 0o644)
        fingerprint = ca.fingerprint(hashes.SHA256()).hex()
        outer = str(uuid.uuid5(uuid.NAMESPACE_URL, 'exvius-ios/profile/' + fingerprint)).upper()
        inner = str(uuid.uuid5(uuid.NAMESPACE_URL, 'exvius-ios/root/' + fingerprint)).upper()
        profile = {'PayloadType': 'Configuration', 'PayloadVersion': 1, 'PayloadUUID': outer,
                   'PayloadIdentifier': 'com.exvius.offline.ios.' + outer,
                   'PayloadDisplayName': 'Exvius Offline iPhone Connection', 'PayloadRemovalDisallowed': False,
                   'PayloadDescription': 'Trust the local Exvius server for gumi.sg and exvius.com.',
                   'PayloadContent': [{'PayloadType': 'com.apple.security.root', 'PayloadVersion': 1,
                       'PayloadUUID': inner, 'PayloadIdentifier': 'com.exvius.offline.root.' + inner,
                       'PayloadDisplayName': ROOT_NAME, 'PayloadCertificateFileName': 'exvius-ios-root.cer',
                       'PayloadContent': der}]}
        _atomic(self.profile, plistlib.dumps(profile), 0o644)
        return {**self.inspect(now=moment), 'leaf_renewed': renewed}

    def inspect(self, *, now=None):
        """No mkdir, repair, or key generation on the query path."""
        required = ('identity.json', 'leaf.pem', 'ca.pem', 'ca.crt', 'exvius-offline.mobileconfig')
        missing = [name for name in required if not self.path(name).is_file()]
        if missing:
            return {'ok': False, 'missing': missing, 'action': 'Run macos_ios_server.py setup.'}
        try:
            ca = x509.load_pem_x509_certificate(self.path('ca.pem').read_bytes())
            leaf = x509.load_pem_x509_certificate(self.leaf.read_bytes())
            leaf.verify_directly_issued_by(ca)
            moment = now or _now()
            valid = all(cert.not_valid_before_utc <= moment < cert.not_valid_after_utc for cert in (ca, leaf))
            return {'ok': valid, 'ca_sha256': ca.fingerprint(hashes.SHA256()).hex(),
                    'leaf_expires': leaf.not_valid_after_utc.isoformat(),
                    'renewal_due': moment >= leaf.not_valid_after_utc - timedelta(days=30)}
        except (ValueError, TypeError, InvalidSignature) as exc:
            return {'ok': False, 'error': str(exc)}
