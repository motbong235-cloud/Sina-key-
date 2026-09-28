"""KHMER SYSTEM payment API — https://pay.khmer-system.com
Official docs: https://khmer-system.com/api-docs

Auth keys:
  - secret_key  (sk_live_...)  — per-merchant secret from dashboard
  - profile_key (PK_...)       — account profile key; if MULTIPLE merchants
                                  you MUST also pass merchant_id

Required for generate:
  - amount (> 0 USD)
  - verify_key (exactly 10 alphanumeric)
  - telegram_user_id (string)
  - secret_key OR profile_key
  - merchant_id (required when using profile_key with multi-merchant account)
"""
from __future__ import annotations

import json
import secrets
import string
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://pay.khmer-system.com"


def _post(path: str, payload: dict, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
            if "code" not in parsed and e.code:
                parsed["code"] = str(e.code)
            if "success" not in parsed:
                parsed["success"] = False
            return parsed
        except Exception:
            return {"success": False, "error": body[:300], "code": str(e.code)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _get(path: str, params: dict, timeout: int = 30) -> dict:
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        BASE + path + "?" + qs,
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
            if "code" not in parsed and e.code:
                parsed["code"] = str(e.code)
            if "success" not in parsed:
                parsed["success"] = False
            return parsed
        except Exception:
            return {"success": False, "error": body[:300], "code": str(e.code)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def make_verify_key() -> str:
    """Exactly 10 alphanumeric characters (required by Khmer System)."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(10))


def _auth_fields(secret_key: str | None, profile_key: str | None) -> dict:
    """Build auth fields. PK_... → profile_key; otherwise secret_key."""
    sk = (secret_key or "").strip()
    pk = (profile_key or "").strip()
    # Prefer explicit profile_key if provided
    if pk:
        return {"profile_key": pk}
    if sk.upper().startswith("PK_"):
        return {"profile_key": sk}
    if sk:
        return {"secret_key": sk}
    return {}


def generate(
    *,
    secret_key: str | None = None,
    amount: float,
    verify_key: str,
    telegram_user_id: str,
    bakong_account_id: str | None = None,
    merchant_name: str | None = None,
    merchant_id: str | None = None,
    machine_id: str | None = None,
    profile_key: str | None = None,
) -> dict:
    auth = _auth_fields(secret_key, profile_key)
    if not auth:
        return {"success": False, "error": "Missing secret_key or profile_key", "code": "INVALID_SECRET_KEY"}

    vkey = (verify_key or "").strip()
    if len(vkey) != 10 or not vkey.isalnum():
        return {
            "success": False,
            "error": "verify_key must be exactly 10 alphanumeric chars",
            "code": "INVALID_VERIFY_KEY_FORMAT",
        }

    amt = float(amount)
    if amt <= 0:
        return {"success": False, "error": "Amount must be > 0", "code": "INVALID_AMOUNT"}

    tg = str(telegram_user_id or "0").strip() or "0"

    payload = {
        **auth,
        "amount": amt,
        "verify_key": vkey,
        "telegram_user_id": tg,
    }
    # Multi-merchant accounts REQUIRE merchant_id (especially with profile_key)
    if merchant_id and str(merchant_id).strip():
        payload["merchant_id"] = str(merchant_id).strip()
    if bakong_account_id and str(bakong_account_id).strip():
        payload["bakong_account_id"] = str(bakong_account_id).strip()
    if merchant_name and str(merchant_name).strip():
        payload["merchant_name"] = str(merchant_name).strip()[:25]
    if machine_id and str(machine_id).strip():
        payload["machine_id"] = str(machine_id).strip()

    return _post("/api/v1/payment/generate", payload)


def check(
    *,
    secret_key: str | None = None,
    verify_key: str,
    telegram_user_id: str,
    profile_key: str | None = None,
    merchant_id: str | None = None,
) -> dict:
    auth = _auth_fields(secret_key, profile_key)
    params = {
        **auth,
        "verify_key": str(verify_key).strip(),
        "telegram_user_id": str(telegram_user_id or "0"),
    }
    if merchant_id and str(merchant_id).strip():
        params["merchant_id"] = str(merchant_id).strip()
    return _get("/api/v1/payment/check", params)


def confirm(
    *,
    secret_key: str | None = None,
    verify_key: str,
    telegram_user_id: str,
    profile_key: str | None = None,
    merchant_id: str | None = None,
) -> dict:
    auth = _auth_fields(secret_key, profile_key)
    payload = {
        **auth,
        "verify_key": str(verify_key).strip(),
        "telegram_user_id": str(telegram_user_id or "0"),
    }
    if merchant_id and str(merchant_id).strip():
        payload["merchant_id"] = str(merchant_id).strip()
    return _post("/api/v1/payment/confirm", payload)
