"""
Storage for encrypted file blobs.

Two backends, chosen by the STORAGE_BACKEND environment variable:
  - "supabase" (default): Supabase Storage via its REST API
  - "local": a folder on disk, for development and tests only

Only encrypted bytes ever pass through here. Every function takes a
server-generated storage key, never a user-supplied name.
"""

import logging
import os
import re
import secrets
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 60
_STORAGE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


class StorageError(Exception):
    """Raised when the storage backend fails or is misconfigured."""


class BlobNotFoundError(StorageError):
    """Raised when a requested blob does not exist."""


def generate_storage_key() -> str:
    # 32 random bytes -> 43 URL-safe characters
    return secrets.token_urlsafe(32)


def _check_storage_key(storage_key: str) -> None:
    if not _STORAGE_KEY_PATTERN.fullmatch(storage_key):
        raise StorageError("Invalid storage key")


def _backend() -> str:
    backend = os.getenv("STORAGE_BACKEND", "supabase").strip().lower()
    if backend not in ("supabase", "local"):
        raise StorageError("Unknown storage backend")
    return backend


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def upload_blob(storage_key: str, data: bytes) -> None:
    _check_storage_key(storage_key)
    if _backend() == "local":
        _local_upload(storage_key, data)
    else:
        _supabase_upload(storage_key, data)


def download_blob(storage_key: str) -> bytes:
    _check_storage_key(storage_key)
    if _backend() == "local":
        return _local_download(storage_key)
    return _supabase_download(storage_key)


def delete_blob(storage_key: str) -> None:
    """Delete a blob. Deleting one that is already gone counts as success,
    so the sweeper can safely retry."""
    _check_storage_key(storage_key)
    if _backend() == "local":
        _local_delete(storage_key)
    else:
        _supabase_delete(storage_key)


# --------------------------------------------------------------------------
# Local backend (development only)
# --------------------------------------------------------------------------


def _local_path(storage_key: str) -> Path:
    root = Path(os.getenv("LOCAL_STORAGE_DIR", ".dev_storage"))
    root.mkdir(parents=True, exist_ok=True)
    return root / storage_key


def _local_upload(storage_key: str, data: bytes) -> None:
    try:
        # "xb" = exclusive create: fails instead of overwriting
        with open(_local_path(storage_key), "xb") as file:
            file.write(data)
    except OSError as exc:
        logger.error("Local storage upload failed: %s", type(exc).__name__)
        raise StorageError("Storage upload failed") from exc


def _local_download(storage_key: str) -> bytes:
    try:
        return _local_path(storage_key).read_bytes()
    except FileNotFoundError as exc:
        raise BlobNotFoundError("Blob not found") from exc
    except OSError as exc:
        logger.error("Local storage download failed: %s", type(exc).__name__)
        raise StorageError("Storage download failed") from exc


def _local_delete(storage_key: str) -> None:
    try:
        _local_path(storage_key).unlink(missing_ok=True)
    except OSError as exc:
        logger.error("Local storage delete failed: %s", type(exc).__name__)
        raise StorageError("Storage delete failed") from exc


# --------------------------------------------------------------------------
# Supabase backend
# --------------------------------------------------------------------------


def _settings() -> tuple[str, str, str]:
    # Read lazily so import order relative to load_dotenv() never matters.
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    bucket = os.getenv("SUPABASE_BUCKET")
    if not url or not key or not bucket:
        raise StorageError("Storage is not configured")
    return url.rstrip("/"), key, bucket


def _headers(key: str, content_type: str | None = None) -> dict:
    headers = {"apikey": key}
    # Legacy service_role keys are JWTs and go in Authorization as well.
    # Newer sb_secret_... keys are not JWTs, so only apikey is sent for them.
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _is_not_found(response: requests.Response) -> bool:
    # Some Storage versions report a missing object as HTTP 400 with a
    # not_found body instead of a plain 404, so check both.
    if response.status_code == 404:
        return True
    return response.status_code == 400 and "not_found" in response.text.lower()


def _supabase_upload(storage_key: str, data: bytes) -> None:
    base, key, bucket = _settings()

    url = f"{base}/storage/v1/object/{bucket}/{storage_key}"
    headers = _headers(key, "application/octet-stream")
    headers["x-upsert"] = "false"  # never overwrite an existing object

    try:
        response = requests.post(
            url, data=data, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        logger.error("Storage upload failed: %s", type(exc).__name__)
        raise StorageError("Storage upload failed") from exc

    if response.status_code not in (200, 201):
        logger.error(
            "Storage upload rejected: status=%s body=%s",
            response.status_code,
            response.text[:200],
        )
        raise StorageError("Storage upload failed")


def _supabase_download(storage_key: str) -> bytes:
    base, key, bucket = _settings()

    url = f"{base}/storage/v1/object/authenticated/{bucket}/{storage_key}"

    try:
        response = requests.get(
            url, headers=_headers(key), timeout=REQUEST_TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        logger.error("Storage download failed: %s", type(exc).__name__)
        raise StorageError("Storage download failed") from exc

    if _is_not_found(response):
        raise BlobNotFoundError("Blob not found")
    if response.status_code != 200:
        logger.error(
            "Storage download rejected: status=%s body=%s",
            response.status_code,
            response.text[:200],
        )
        raise StorageError("Storage download failed")

    return response.content


def _supabase_delete(storage_key: str) -> None:
    base, key, bucket = _settings()

    url = f"{base}/storage/v1/object/{bucket}/{storage_key}"

    try:
        response = requests.delete(
            url, headers=_headers(key), timeout=REQUEST_TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        logger.error("Storage delete failed: %s", type(exc).__name__)
        raise StorageError("Storage delete failed") from exc

    if _is_not_found(response):
        return
    if response.status_code not in (200, 204):
        logger.error(
            "Storage delete rejected: status=%s body=%s",
            response.status_code,
            response.text[:200],
        )
        raise StorageError("Storage delete failed")
