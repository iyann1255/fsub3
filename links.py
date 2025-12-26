import base64
import hmac
import hashlib

def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")

def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

def sign_payload(secret_key: str, payload: str) -> str:
    mac = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).digest()
    return _b64e(mac)

def make_token(secret_key: str, file_id: str) -> str:
    # payload = file_id
    sig = sign_payload(secret_key, file_id)
    raw = f"{file_id}.{sig}".encode()
    return _b64e(raw)

def parse_token(secret_key: str, token: str) -> str | None:
    try:
        raw = _b64d(token).decode()
        file_id, sig = raw.rsplit(".", 1)
        good = sign_payload(secret_key, file_id)
        if hmac.compare_digest(sig, good):
            return file_id
        return None
    except Exception:
        return None
