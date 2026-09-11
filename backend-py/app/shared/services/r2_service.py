"""Cloudflare R2 storage (S3-compatible), equivalent to
backend/src/shared/services/r2.service.ts.

Two clients on purpose: `_r2_client` for uploads/deletes (R2_ENDPOINT), and
`_signing_client` only to presign URLs (R2_PUBLIC_ENDPOINT if set, else
falls back to R2_ENDPOINT) - a presigned URL's signature is bound to the
host it was signed against, so a self-hosted deployment behind a private
network needs a distinct public-facing host to sign against.
"""

from __future__ import annotations

import uuid
from typing import Literal
from urllib.parse import urlparse

import boto3
from botocore.client import Config

from app.logging import get_logger
from app.settings import settings

logger = get_logger(__name__)

Folder = Literal["resumes", "logos"]

# Whitelist mapping mimetype -> extension for server-controlled filenames -
# never trust a client-supplied filename (prevents e.g. a .html/.svg upload
# disguised as something else).
_EXT_BY_MIME = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}

_INLINE_SAFE_MIME_TYPES_FOR_LOGOS = {"image/png", "image/jpeg", "image/webp"}


def _build_client(endpoint: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="us-east-1",  # arbitrary/ignored by R2
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=5,
            read_timeout=10,
            retries={"max_attempts": 2},
        ),
    )


_r2_client = _build_client(settings.r2_endpoint)
_signing_client = _build_client(settings.r2_public_endpoint or settings.r2_endpoint)


def _public_url(file_name: str) -> str:
    return f"{settings.r2_public_url.rstrip('/')}/{file_name}"


def upload_file(*, content: bytes, content_type: str, folder: Folder = "resumes") -> str:
    ext = _EXT_BY_MIME.get(content_type, "")
    file_name = f"{folder}/{uuid.uuid4().hex}{ext}"

    is_inline_safe_logo = folder == "logos" and content_type in _INLINE_SAFE_MIME_TYPES_FOR_LOGOS
    disposition = "inline" if is_inline_safe_logo else "attachment"

    _r2_client.put_object(
        Bucket=settings.r2_bucket_name,
        Key=file_name,
        Body=content,
        ContentType=content_type,
        ContentDisposition=disposition,
    )
    return _public_url(file_name)


def download_file(key: str) -> bytes:
    response = _r2_client.get_object(Bucket=settings.r2_bucket_name, Key=key)
    return response["Body"].read()


def extract_key_from_url(file_url: str) -> str | None:
    base = settings.r2_public_url.rstrip("/")
    if not file_url.startswith(base):
        return None
    key = file_url[len(base) :].lstrip("/")
    return urlparse(f"https://x/{key}").path.lstrip("/")


def sign_url(file_url: str | None) -> str | None:
    """Converts a stored (unsigned) public-style URL into a short-lived
    presigned GET URL. Never raises: a signing failure logs and returns
    None so callers can degrade to "no resume" instead of a 500."""
    if file_url is None:
        return None

    key = extract_key_from_url(file_url)
    if key is None:
        return file_url  # points outside our bucket - pass through unchanged

    try:
        return _signing_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.r2_bucket_name, "Key": key},
            ExpiresIn=settings.signed_url_ttl_seconds,
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to sign url for key=%s", key)
        return None


def delete_by_url(file_url: str | None) -> None:
    if file_url is None:
        return
    key = extract_key_from_url(file_url)
    if key is None:
        return
    _r2_client.delete_object(Bucket=settings.r2_bucket_name, Key=key)
