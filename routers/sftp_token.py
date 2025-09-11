import os
import json
import base64
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from auth import require_auth
import db

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception as e:  # pragma: no cover
    AESGCM = None


router = APIRouter()


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _get_shared_key() -> bytes:
    key_b64 = os.getenv("SFTP_SHARED_KEY", "").strip()
    if not key_b64:
        raise RuntimeError("SFTP_SHARED_KEY is not set")
    try:
        key = _b64url_decode(key_b64)
    except Exception:
        raise RuntimeError("SFTP_SHARED_KEY must be base64url encoded 32 bytes")
    if len(key) not in (16, 24, 32):
        raise RuntimeError("SFTP_SHARED_KEY must decode to 16/24/32 bytes (AES key)")
    return key


def _encrypt_payload(payload: dict) -> str:
    if AESGCM is None:
        raise RuntimeError("cryptography is required for AES-GCM encryption")
    key = _get_shared_key()
    aes = AESGCM(key)
    nonce = os.urandom(12)
    # Additional authenticated data to bind token format/version
    aad = b"sftp.v1"
    pt = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ct = aes.encrypt(nonce, pt, aad)
    return "v1." + _b64url_encode(nonce) + "." + _b64url_encode(ct)


def _mint_for_values(host: str, username: str, password: str, user_name: str) -> str:
    now = int(time.time())
    payload = {
        "host": host,
        "username": username,
        "password": password,
        "iat": now,
        "exp": now + 120,  # 2 minutes
        "by": user_name,
    }
    return _encrypt_payload(payload)


@router.post("/api/sftp/mint")
async def mint_token(request: Request, auth=Depends(require_auth)):
    """
    Mint a short-lived encrypted token for the SFTP browser app.

    Accepts either:
      - { "host_id": <int> }   -> credentials are looked up server-side
      - { "host": str, "username": str, "password": str } (legacy)
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")

    user = request.session.get("user") or {}
    user_name = user.get("username", "")

    # Preferred: host_id lookup (avoids exposing credentials to the browser)
    host_id: Optional[int] = body.get("host_id") if isinstance(body, dict) else None
    if isinstance(host_id, int) and host_id > 0:
        conn = db.get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM hosts WHERE id = ? AND (user_id = ? OR ?)",
            (host_id, user.get("id", 0), int(bool(user.get("is_admin"))))
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="host not found")
        token = _mint_for_values(row["host"], row["username"], row["password"], user_name)
        return JSONResponse({"token": token})

    # Legacy: accept explicit values (still minted server-side; never placed in the URL)
    host = (body.get("host") or "").strip() if isinstance(body, dict) else ""
    username = (body.get("username") or "").strip() if isinstance(body, dict) else ""
    password = (body.get("password") or "") if isinstance(body, dict) else ""
    if not host or not username or not password:
        raise HTTPException(status_code=400, detail="missing host/username/password or host_id")
    token = _mint_for_values(host, username, password, user_name)
    return JSONResponse({"token": token})

