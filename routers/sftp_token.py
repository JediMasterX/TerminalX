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


def _select_aes_key() -> bytes:
    # Prefer TOKEN_SECRET (string) → SHA-256 to 32 bytes to match Node server
    token_secret = os.getenv("TOKEN_SECRET", "").strip()
    if token_secret:
        import hashlib
        return hashlib.sha256(token_secret.encode("utf-8")).digest()

    # Fallback: SFTP_SHARED_KEY as base64url-encoded key bytes (16/24/32)
    key_b64 = os.getenv("SFTP_SHARED_KEY", "").strip()
    if not key_b64:
        raise RuntimeError("Either TOKEN_SECRET or SFTP_SHARED_KEY must be set")
    try:
        key = _b64url_decode(key_b64)
    except Exception:
        raise RuntimeError("SFTP_SHARED_KEY must be base64url encoded 16/24/32 bytes")
    if len(key) not in (16, 24, 32):
        raise RuntimeError("SFTP_SHARED_KEY must decode to 16/24/32 bytes (AES key)")
    return key


def _encrypt_payload(payload: dict) -> str:
    """Encrypt payload producing Node-compatible token: v1.<iv>.<ct>.<tag>.
    - AES-*-GCM with 12-byte IV
    - No AAD
    - Tag length is 16 bytes split from the end of ciphertext
    """
    if AESGCM is None:
        raise RuntimeError("cryptography is required for AES-GCM encryption")
    key = _select_aes_key()
    aes = AESGCM(key)
    iv = os.urandom(12)
    pt = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ct_with_tag = aes.encrypt(iv, pt, None)  # associated_data=None to match Node
    if len(ct_with_tag) < 17:
        raise RuntimeError("encryption failed: ciphertext too short")
    tag = ct_with_tag[-16:]
    ct = ct_with_tag[:-16]
    return "v1." + _b64url_encode(iv) + "." + _b64url_encode(ct) + "." + _b64url_encode(tag)


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
