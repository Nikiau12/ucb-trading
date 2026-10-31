"""Read-only BingX Agent API checks for referral eligibility."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Callable

import requests


DEFAULT_BASE_URL = "https://open-api.bingx.com"
RELATION_PATH = "/openApi/agent/v1/account/inviteRelationCheck"


def _is_true(value) -> bool:
    return value is True or str(value).strip().lower() == "true"


def verify_direct_referral(
    bingx_uid: str,
    *,
    api_key: str | None = None,
    api_secret: str | None = None,
    base_url: str | None = None,
    request_get: Callable | None = None,
    now_ms: int | None = None,
) -> dict:
    """Return verified, not_eligible, or unavailable without exposing secrets.

    Only the read-only invitation-relationship endpoint is called. A temporary
    BingX or network failure is deliberately different from a negative result:
    callers can keep the claim pending for manual review instead of rejecting it.
    """

    uid = str(bingx_uid or "").strip()
    if not uid.isdigit() or not 6 <= len(uid) <= 20:
        return {"status": "not_eligible", "reason": "invalid_uid"}

    key = api_key if api_key is not None else os.getenv("BINGX_AGENT_API_KEY", "")
    secret = (
        api_secret
        if api_secret is not None
        else os.getenv("BINGX_AGENT_API_SECRET", "")
    )
    if not key or not secret:
        return {"status": "unavailable", "reason": "credentials_missing"}

    api_base = (
        base_url
        if base_url is not None
        else os.getenv("BINGX_AGENT_API_BASE", DEFAULT_BASE_URL)
    ).rstrip("/")
    if not api_base.startswith("https://"):
        return {"status": "unavailable", "reason": "invalid_base_url"}

    business_params = {
        "recvWindow": 5000,
        "timestamp": int(now_ms if now_ms is not None else time.time() * 1000),
        "uid": uid,
    }
    # BingX validates the signature against the transmitted parameter order.
    # Keep the request in the same ASCII-sorted order used for the HMAC input.
    signed_params = sorted((key, str(value)) for key, value in business_params.items())
    canonical = "&".join(f"{key}={value}" for key, value in signed_params)
    signature = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    params = [*signed_params, ("signature", signature)]
    get = request_get or requests.get

    try:
        response = get(
            f"{api_base}{RELATION_PATH}",
            params=params,
            headers={
                "X-BX-APIKEY": key,
                "X-SOURCE-KEY": "BX-AI-SKILL",
            },
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, TypeError, ValueError):
        return {"status": "unavailable", "reason": "request_failed"}

    if not isinstance(payload, dict):
        return {"status": "unavailable", "reason": "invalid_response"}
    code = payload.get("code")
    if str(code) != "0":
        safe_code = str(code) if str(code).isdigit() else "unknown"
        return {"status": "unavailable", "reason": f"bingx_code_{safe_code}"}

    data = payload.get("data")
    if not isinstance(data, dict) or str(data.get("uid") or "") != uid:
        return {"status": "unavailable", "reason": "invalid_response"}
    if _is_true(data.get("inviteResult")) and _is_true(data.get("directInvitation")):
        return {"status": "verified", "reason": "direct_referral"}
    reason = "indirect_referral" if _is_true(data.get("inviteResult")) else "not_referred"
    return {"status": "not_eligible", "reason": reason}
