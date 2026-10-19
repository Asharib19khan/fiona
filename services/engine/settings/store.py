"""Per-workspace settings, with secrets sealed by AES-GCM.

A secret is bound to its workspace and setting name (they are the AES-GCM associated data), so
ciphertext copied into another workspace's row does not decrypt. The key comes from
SETTINGS_ENCRYPTION_KEY (32 bytes, base64url); without it, secrets cannot be stored or read.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import secrets
from datetime import datetime
from typing import Any

import psycopg
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from engine.ledger import db

_PREFIX = "v1"


class SecretStorageUnavailable(RuntimeError):
    """SETTINGS_ENCRYPTION_KEY is missing or malformed, or a stored secret no longer opens."""


def _key() -> bytes:
    raw = os.environ.get("SETTINGS_ENCRYPTION_KEY", "").strip()
    if not raw:
        raise SecretStorageUnavailable("SETTINGS_ENCRYPTION_KEY is not set on the engine.")
    try:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except (binascii.Error, ValueError) as exc:
        raise SecretStorageUnavailable("SETTINGS_ENCRYPTION_KEY must be base64url.") from exc
    if len(key) != 32:
        raise SecretStorageUnavailable("SETTINGS_ENCRYPTION_KEY must decode to 32 bytes.")
    return key


def storage_ready() -> bool:
    try:
        _key()
    except SecretStorageUnavailable:
        return False
    return True


def _aad(tenant_id: str, name: str) -> bytes:
    return f"fiona/tenant-settings/{tenant_id}/{name}".encode()


def seal(tenant_id: str, name: str, secret: str) -> str:
    nonce = secrets.token_bytes(12)
    sealed = AESGCM(_key()).encrypt(nonce, secret.encode("utf-8"), _aad(tenant_id, name))
    encode = base64.urlsafe_b64encode
    return f"{_PREFIX}.{encode(nonce).decode()}.{encode(sealed).decode()}"


def unseal(tenant_id: str, name: str, token: str) -> str:
    try:
        prefix, nonce, sealed = token.split(".")
        if prefix != _PREFIX:
            raise ValueError(prefix)
        plain = AESGCM(_key()).decrypt(
            base64.urlsafe_b64decode(nonce), base64.urlsafe_b64decode(sealed), _aad(tenant_id, name)
        )
    except (ValueError, binascii.Error, InvalidTag) as exc:
        raise SecretStorageUnavailable("The stored secret could not be opened.") from exc
    return plain.decode("utf-8")


def read(conn: psycopg.Connection, tenant_id: str, name: str) -> dict[str, Any] | None:
    with db.tenant_session(conn, tenant_id):
        row = conn.execute(
            "select value, secret_ciphertext, updated_by, updated_at from tenant_settings"
            " where key = %s",
            (name,),
        ).fetchone()
    if row is None:
        return None
    value, ciphertext, updated_by, updated_at = row
    return {
        "value": value or {},
        "ciphertext": ciphertext,
        "updated_by": updated_by,
        "updated_at": updated_at,
    }


def write(
    conn: psycopg.Connection,
    tenant_id: str,
    name: str,
    value: dict[str, Any],
    *,
    ciphertext: str | None,
    updated_by: str,
    now: datetime,
) -> None:
    with db.tenant_session(conn, tenant_id):
        conn.execute(
            "insert into tenant_settings (tenant_id, key, value, secret_ciphertext, updated_by,"
            " updated_at) values (%s, %s, %s, %s, %s, %s)"
            " on conflict (tenant_id, key) do update set value = excluded.value,"
            " secret_ciphertext = excluded.secret_ciphertext, updated_by = excluded.updated_by,"
            " updated_at = excluded.updated_at",
            (tenant_id, name, json.dumps(value), ciphertext, updated_by, now),
        )
