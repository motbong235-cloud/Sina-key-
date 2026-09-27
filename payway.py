
"""ABA PayWay helpers — HMAC-SHA512 + QR + check transaction."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone


def req_time() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def hmac_hash(api_key: str, *parts) -> str:
    raw = "".join("" if p is None else str(p) for p in parts)
    digest = hmac.new(api_key.encode("utf-8"), raw.encode("utf-8"), hashlib.sha512).digest()
    return base64.b64encode(digest).decode("utf-8")


def b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("utf-8")


def base_url(sandbox: bool) -> str:
    if sandbox:
        return "https://checkout-sandbox.payway.com.kh"
    return "https://checkout.payway.com.kh"


def post_json(url: str, payload: dict, timeout: int = 30) -> dict:
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
            return {"status": {"code": str(e.code), "message": body[:300]}}
    except Exception as e:
        return {"status": {"code": "err", "message": str(e)}}


def generate_qr(
    *,
    merchant_id: str,
    api_key: str,
    tran_id: str,
    amount: float,
    currency: str = "USD",
    sandbox: bool = True,
    callback_url: str | None = None,
    first_name: str = "Customer",
    last_name: str = "Sina",
    phone: str = "",
    email: str = "",
    items_name: str = "Order",
    lifetime: int = 30,
) -> dict:
    """Call ABA PayWay generate-qr API. Returns dict with qrImage, qrString, etc."""
    amount_str = f"{float(amount):.2f}" if currency.upper() == "USD" else str(int(amount))
    rt = req_time()
    purchase_type = "purchase"
    payment_option = "abapay_khqr"
    items = b64(json.dumps([{"name": items_name[:80], "quantity": 1, "price": float(amount)}]))
    cb = b64(callback_url) if callback_url else ""
    return_deeplink = ""
    custom_fields = ""
    return_params = ""
    payout = ""
    qr_image_template = "template3_color"

    # hash order from official docs
    h = hmac_hash(
        api_key,
        rt,
        merchant_id,
        tran_id,
        amount_str,
        items,
        first_name,
        last_name,
        email,
        phone,
        purchase_type,
        payment_option,
        cb,
        return_deeplink,
        currency.upper(),
        custom_fields,
        return_params,
        payout,
        lifetime,
        qr_image_template,
    )

    payload = {
        "req_time": rt,
        "merchant_id": merchant_id,
        "tran_id": tran_id[:20],
        "amount": amount_str,
        "items": items,
        "first_name": first_name[:20] or "Customer",
        "last_name": last_name[:20] or "Sina",
        "email": email,
        "phone": phone,
        "purchase_type": purchase_type,
        "payment_option": payment_option,
        "callback_url": cb or None,
        "return_deeplink": None,
        "currency": currency.upper(),
        "custom_fields": None,
        "return_params": None,
        "payout": None,
        "lifetime": lifetime,
        "qr_image_template": qr_image_template,
        "hash": h,
    }
    url = base_url(sandbox) + "/api/payment-gateway/v1/payments/generate-qr"
    return post_json(url, payload)


def check_transaction(
    *,
    merchant_id: str,
    api_key: str,
    tran_id: str,
    sandbox: bool = True,
) -> dict:
    rt = req_time()
    h = hmac_hash(api_key, rt, merchant_id, tran_id)
    payload = {
        "req_time": rt,
        "merchant_id": merchant_id,
        "tran_id": tran_id[:20],
        "hash": h,
    }
    url = base_url(sandbox) + "/api/payment-gateway/v1/payments/check-transaction-2"
    return post_json(url, payload)
