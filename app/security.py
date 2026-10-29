"""Request authentication for webhooks and admin endpoints."""
import base64
import hashlib
import hmac
import time

from fastapi import HTTPException, Request

from .config import Settings

_DECODE = {"%3A": ":", "%2F": "/", "%3F": "?", "%40": "@", "%21": "!", "%24": "$",
           "%27": "'", "%28": "(", "%29": ")", "%2A": "*", "%2C": ",", "%3B": ";"}


def verify_signature_v3(settings: Settings, request: Request, body: bytes) -> bool:
    """HubSpot signature v3: base64(HMAC-SHA256(secret, METHOD + URL + BODY + TIMESTAMP))."""
    sig = request.headers.get("X-HubSpot-Signature-v3", "")
    ts = request.headers.get("X-HubSpot-Request-Timestamp", "")
    if not (sig and ts and settings.hubspot_client_secret and settings.public_base_url):
        return False
    try:
        if abs(time.time() * 1000 - int(ts)) > 5 * 60 * 1000:
            return False
    except ValueError:
        return False
    url = settings.public_base_url.rstrip("/") + request.url.path
    if request.url.query:
        url += "?" + request.url.query
    for enc, dec in _DECODE.items():
        url = url.replace(enc, dec).replace(enc.lower(), dec)
    message = request.method.encode() + url.encode() + body + ts.encode()
    digest = hmac.new(settings.hubspot_client_secret.encode(), message, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), sig)


def authorize_webhook(settings: Settings, request: Request, body: bytes, secret: str) -> None:
    if request.headers.get("X-HubSpot-Signature-v3"):
        if not verify_signature_v3(settings, request, body):
            raise HTTPException(401, "invalid HubSpot signature")
        return
    if not settings.webhook_secret or not hmac.compare_digest(secret.encode(), settings.webhook_secret.encode()):
        raise HTTPException(401, "invalid webhook secret")


def authorize_admin(settings: Settings, provided: str | None) -> None:
    if not provided or not hmac.compare_digest(provided.encode(), settings.admin_api_key.encode()):
        raise HTTPException(401, "invalid or missing X-API-Secret")

