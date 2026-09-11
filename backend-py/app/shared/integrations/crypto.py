"""AES-256-GCM encryption + signed OAuth state tokens, equivalent to
backend/src/shared/integrations/crypto.ts.

Encrypted payload format is `iv_b64:auth_tag_b64:ciphertext_b64`, matching
the TS implementation exactly (12-byte IV, 16-byte GCM tag). Signed state
tokens reuse ENCRYPTION_KEY as the HMAC key too, same as the TS code - a
hand-rolled JWT-lite, not a real JWT, for the OAuth `state` CSRF parameter.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.settings import settings

_KEY = base64.b64decode(settings.encryption_key)


class StateTokenError(Exception):
    pass


def encrypt(plaintext: str) -> str:
    iv = os.urandom(12)
    aesgcm = AESGCM(_KEY)
    ciphertext_and_tag = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    ciphertext, tag = ciphertext_and_tag[:-16], ciphertext_and_tag[-16:]
    return ":".join(
        base64.b64encode(part).decode("ascii") for part in (iv, tag, ciphertext)
    )


def decrypt(payload: str) -> str:
    parts = payload.split(":")
    if len(parts) != 3:
        raise ValueError("Malformed encrypted payload")
    iv, tag, ciphertext = (base64.b64decode(part) for part in parts)
    aesgcm = AESGCM(_KEY)
    plaintext = aesgcm.decrypt(iv, ciphertext + tag, None)
    return plaintext.decode("utf-8")


@dataclass(frozen=True)
class StatePayload:
    user_id: int


def sign_state(user_id: int, ttl_seconds: int) -> str:
    body = {
        "userId": user_id,
        "nonce": os.urandom(8).hex(),
        "exp": int(time.time() * 1000) + ttl_seconds * 1000,
    }
    body_b64 = base64.urlsafe_b64encode(json.dumps(body).encode("utf-8")).rstrip(b"=").decode("ascii")
    signature = hmac.new(_KEY, body_b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body_b64}.{signature}"


def verify_state(token: str) -> StatePayload:
    try:
        body_b64, signature = token.split(".")
    except ValueError as exc:
        raise StateTokenError("Malformed state token") from exc

    expected_signature = hmac.new(_KEY, body_b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise StateTokenError("Invalid state token signature")

    padding = "=" * (-len(body_b64) % 4)
    body = json.loads(base64.urlsafe_b64decode(body_b64 + padding))
    if int(time.time() * 1000) > body["exp"]:
        raise StateTokenError("State token expired")

    return StatePayload(user_id=body["userId"])
