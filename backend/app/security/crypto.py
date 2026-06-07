"""AES-256-GCM encryption at rest for sensitive patient data (PDPO DPP4 / GDPR Art.32).

When ``settings.encrypt_at_rest`` is on, sensitive fields are encrypted with a
256-bit key *before* they are written to MongoDB and transparently decrypted on
read, so health text (check-in notes, care-plan text, phone numbers, transcripts)
never sits in the database as plaintext.

Design choices:
- **AES-256-GCM** (authenticated encryption): confidentiality + tamper detection.
- **Fail closed:** if encryption is enabled but the key or the ``cryptography``
  library is missing/invalid, ``verify_config()`` raises at startup rather than
  silently storing plaintext.
- **Decrypt-tolerant:** values that are not in our envelope format are returned
  unchanged, so turning encryption on/off needs no data migration and never breaks
  reads of pre-existing rows.
- **Key handling:** the key comes from ``CARELOOP_DATA_KEY`` (base64 or hex, 32
  bytes). In production this should be sourced from a managed KMS / secret store;
  ``_load_key()`` is the single seam to swap in a KMS client.

Envelope format (string):  ``enc::v1::<base64(nonce[12] || ciphertext||tag)>``
"""

from __future__ import annotations

import base64
import logging
import os
from functools import lru_cache

from ..config import settings

log = logging.getLogger("careloop.crypto")

_PREFIX = "enc::v1::"
_NONCE_BYTES = 12  # 96-bit nonce, the GCM standard


def enabled() -> bool:
    return bool(settings.encrypt_at_rest)


def _decode_key(raw: str) -> bytes:
    """Decode a 32-byte key given as base64 or hex; raise if it isn't 32 bytes."""
    raw = raw.strip()
    if not raw:
        raise ValueError("CARELOOP_DATA_KEY is empty")
    key: bytes | None = None
    # Try base64 (standard and urlsafe), then hex.
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            candidate = decoder(raw + "=" * (-len(raw) % 4))
            if len(candidate) == 32:
                key = candidate
                break
        except Exception:  # noqa: BLE001
            pass
    if key is None:
        try:
            candidate = bytes.fromhex(raw)
            if len(candidate) == 32:
                key = candidate
        except ValueError:
            pass
    if key is None or len(key) != 32:
        raise ValueError(
            "CARELOOP_DATA_KEY must decode to exactly 32 bytes (AES-256). "
            "Generate one with: python -c \"import secrets,base64;"
            "print(base64.b64encode(secrets.token_bytes(32)).decode())\""
        )
    return key


@lru_cache(maxsize=1)
def _load_key() -> bytes:
    """Return the 32-byte data key. KMS integration would replace this body."""
    return _decode_key(settings.data_encryption_key)


@lru_cache(maxsize=1)
def _aesgcm():
    """Construct the AESGCM cipher, importing ``cryptography`` lazily."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM(_load_key())


def verify_config() -> None:
    """Fail closed at startup if encryption is enabled but unusable."""
    if not enabled():
        return
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "CARELOOP_ENCRYPT_AT_REST is on but the 'cryptography' package is not "
            "installed. Run: pip install cryptography"
        ) from exc
    _load_key()  # raises ValueError on a bad/missing key
    # Round-trip self-test so we never start in a state that can encrypt but not decrypt.
    token = encrypt_str("careloop-selftest")
    if decrypt_str(token) != "careloop-selftest":
        raise RuntimeError("Encryption self-test failed; check CARELOOP_DATA_KEY.")
    log.info("Encryption at rest: enabled (AES-256-GCM).")


def is_envelope(value: object) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt_str(plaintext: str) -> str:
    """Encrypt a string into the envelope format. No-op passthrough when disabled."""
    if not enabled() or plaintext is None:
        return plaintext
    if is_envelope(plaintext):
        return plaintext  # already encrypted
    nonce = os.urandom(_NONCE_BYTES)
    ct = _aesgcm().encrypt(nonce, plaintext.encode("utf-8"), None)
    return _PREFIX + base64.b64encode(nonce + ct).decode("ascii")


def decrypt_str(value: str) -> str:
    """Decrypt an envelope string. Tolerant: returns non-envelope values unchanged."""
    if not is_envelope(value):
        return value
    try:
        blob = base64.b64decode(value[len(_PREFIX):])
        nonce, ct = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
        return _aesgcm().decrypt(nonce, ct, None).decode("utf-8")
    except Exception:  # noqa: BLE001 - bad key / corrupted data
        log.warning("Failed to decrypt a field; returning the stored value as-is.")
        return value


def encrypt_fields(doc: dict, fields: tuple[str, ...]) -> dict:
    """Return a shallow copy of ``doc`` with the named string fields encrypted."""
    if not enabled():
        return doc
    out = dict(doc)
    for f in fields:
        v = out.get(f)
        if isinstance(v, str) and v:
            out[f] = encrypt_str(v)
    return out


def decrypt_fields(doc: dict, fields: tuple[str, ...]) -> dict:
    """Return a shallow copy of ``doc`` with the named fields decrypted (tolerant)."""
    out = dict(doc)
    for f in fields:
        v = out.get(f)
        if isinstance(v, str) and v:
            out[f] = decrypt_str(v)
    return out
