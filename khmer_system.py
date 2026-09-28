"""KHMER SYSTEM payment API — https://khmer-system.com/aba-api

Mirrors the exact request/response shape used by KaiJakLikeBot's working
integration (_aba_create / _aba_check_detail in kaijaklike_bot.py):
  POST /aba-api/generate-qr   {api_key, merchant_id, username, amount}
  POST /aba-api/check-payment {api_key, merchant_id, payment_id}
There is no separate "confirm" call and no verify_key/telegram_user_id —
those belonged to a different (non-working) API shape used before.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "https://khmer-system.com"
CREATE_URL = f"{BASE}/aba-api/generate-qr"
CHECK_URL = f"{BASE}/aba-api/check-payment"


def _post(url: str, payload: dict, timeout: int = 20) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
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
            return {"ok": False, "error": f"HTTP {e.code}: {body[:300]}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def generate(api_key: str, merchant_id: str, username: str, amount: float) -> dict:
    """Returns the raw response dict on success — keys typically include
    payment_id, card_image (or qr_image), pay_url. On failure returns
    {"ok": False, "error": "..."}."""
    if not api_key or not merchant_id:
        return {"ok": False, "error": "KHMER_API_KEY / KHMER_MERCHANT_ID មិនបានកំណត់"}
    return _post(CREATE_URL, {
        "api_key": api_key,
        "merchant_id": merchant_id,
        "username": username or "guest",
        "amount": round(float(amount), 2),
    })


def is_paid(check_resp: dict) -> bool:
    """Convenience wrapper — check_resp is the dict returned by check()."""
    return bool(check_resp and check_resp.get("ok"))


def check(api_key: str, merchant_id: str, payment_id: str) -> dict:
    """Returns {"ok": bool, "status": str, "amount": float|None, "raw": dict}."""
    out = {"ok": False, "status": "", "amount": None, "raw": {}}
    if not payment_id:
        return out
    data = _post(CHECK_URL, {
        "api_key": api_key,
        "merchant_id": merchant_id,
        "payment_id": payment_id,
    })
    out["raw"] = data if isinstance(data, dict) else {}
    st = str(data.get("status") or "").strip()
    out["status"] = st
    out["ok"] = bool(data.get("ok")) and st.upper() == "PAID"
    amt = data.get("amount") or data.get("paid_amount") or data.get("total")
    if amt is not None:
        try:
            out["amount"] = round(float(amt), 2)
        except (TypeError, ValueError):
            pass
    return out
