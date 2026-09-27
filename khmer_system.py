"""KHMER SYSTEM payment API — https://pay.khmer-system.com"""
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
            return json.loads(body)
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
            return json.loads(body)
        except Exception:
            return {"success": False, "error": body[:300], "code": str(e.code)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def make_verify_key() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(10))


def generate(
    *,
    secret_key: str,
    amount: float,
    verify_key: str,
    telegram_user_id: str,
    bakong_account_id: str | None = None,
    merchant_name: str | None = None,
) -> dict:
    payload = {
        "secret_key": secret_key,
        "amount": float(amount),
        "verify_key": verify_key,
        "telegram_user_id": str(telegram_user_id),
    }
    if bakong_account_id:
        payload["bakong_account_id"] = bakong_account_id
    if merchant_name:
        payload["merchant_name"] = merchant_name
    return _post("/api/v1/payment/generate", payload)


def check(*, secret_key: str, verify_key: str, telegram_user_id: str) -> dict:
    return _get(
        "/api/v1/payment/check",
        {
            "secret_key": secret_key,
            "verify_key": verify_key,
            "telegram_user_id": str(telegram_user_id),
        },
    )


def confirm(*, secret_key: str, verify_key: str, telegram_user_id: str) -> dict:
    return _post(
        "/api/v1/payment/confirm",
        {
            "secret_key": secret_key,
            "verify_key": verify_key,
            "telegram_user_id": str(telegram_user_id),
        },
    )
