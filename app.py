#!/usr/bin/env python3
"""Sina Key — website លក់ Mode / DNS / Key file"""
import json
import os
import secrets
import time
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    send_from_directory,
    send_file,
)
from werkzeug.utils import secure_filename

import payway
import khmer_system

BASE = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE / "data")))
DB_PATH = DATA_DIR / "db.json"
# uploads on same persistent disk when DATA_DIR is set (Render)
UPLOAD_DIR = DATA_DIR / "uploads"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# seed DB once if missing
_seed = BASE / "data" / "db.json"
if not DB_PATH.exists() and _seed.exists():
    DB_PATH.write_text(_seed.read_text(encoding="utf-8"), encoding="utf-8")


ALLOWED_EXT = {
    "txt", "zip", "rar", "7z", "mobileconfig", "conf", "cfg", "json", "key",
    "pem", "p12", "mobileprovision", "ipa", "apk", "dat", "bin", "dns", "mode",
}


def allowed_file(filename: str) -> bool:
    if "." not in filename:
        return True  # allow extensionless keys
    return filename.rsplit(".", 1)[-1].lower() in ALLOWED_EXT


def normalize_stock_item(item):
    """Return dict form for stock entry."""
    if isinstance(item, dict):
        return item
    return {"type": "text", "value": str(item)}


def stock_label(item):
    item = normalize_stock_item(item)
    if item.get("type") == "file":
        return item.get("name") or item.get("path") or "file"
    return (item.get("value") or "")[:80]


app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(24))


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def db_read():
    if not DB_PATH.exists():
        default = BASE / "data" / "db.json"
        if default.exists() and default != DB_PATH:
            DB_PATH.write_text(default.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            return {"settings": {}, "categories": [], "products": [], "orders": [], "next_order": 1001}
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def db_write(data):
    tmp = DB_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(DB_PATH)


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        return fn(*args, **kwargs)

    return wrapper


# ---------- Pages ----------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/admin")
def admin_page():
    return render_template("admin.html")


@app.route("/order/<order_id>")
def order_page(order_id):
    return render_template("index.html")


# ---------- Public API ----------
@app.route("/api/catalog")
def catalog():
    d = db_read()
    products = [p for p in d.get("products", []) if p.get("active", True)]
    cats = sorted(d.get("categories", []), key=lambda c: c.get("sort", 99))
    return jsonify({
        "ok": True,
        "settings": {
            "SITE_NAME": d.get("settings", {}).get("SITE_NAME", "Sina Key"),
            "SITE_TAGLINE": d.get("settings", {}).get("SITE_TAGLINE", ""),
            "TELEGRAM": d.get("settings", {}).get("TELEGRAM", ""),
            "CONTACT_NOTE": d.get("settings", {}).get("CONTACT_NOTE", ""),
            "PAYMENT_QR": d.get("settings", {}).get("PAYMENT_QR", ""),
            "BAKONG_ID": d.get("settings", {}).get("BAKONG_ID", ""),
            "SHOP_NAME": d.get("settings", {}).get("SHOP_NAME", "Sina Key"),
            "PAYMENT_NOTE": d.get("settings", {}).get("PAYMENT_NOTE", "ស្កេន KHQR បង់តាមតម្លៃ product · រួចចុច បានបង់ហើយ"),
            "AUTO_DELIVER": d.get("settings", {}).get("AUTO_DELIVER", True),
        },
        "categories": cats,
        "products": products,
    })


def _pop_stock_item(d, product_id):
    """Take one stock item (file or text). Returns (delivery, delivery_file)."""
    delivery = None
    delivery_file = None
    stock_map = d.get("stock_files") or {}
    keys = stock_map.get(str(product_id)) or stock_map.get(product_id) or []
    if isinstance(keys, list) and keys:
        raw = keys.pop(0)
        stock_map[str(product_id)] = keys
        d["stock_files"] = stock_map
        item = normalize_stock_item(raw)
        if item.get("type") == "file":
            delivery_file = {"name": item.get("name"), "path": item.get("path")}
            delivery = f"[FILE] {item.get('name')}"
        else:
            delivery = item.get("value") or str(raw)
    return delivery, delivery_file


def _payment_info(d):
    s = d.get("settings") or {}
    return {
        "PAYMENT_QR": s.get("PAYMENT_QR") or "",
        "BAKONG_ID": s.get("BAKONG_ID") or "",
        "SHOP_NAME": s.get("SHOP_NAME") or s.get("SITE_NAME") or "Sina Key",
        "PAYMENT_NOTE": s.get("PAYMENT_NOTE") or "ស្កេន KHQR បង់តាមតម្លៃ · រួចចុច បានបង់ហើយ",
        "AUTO_DELIVER": bool(s.get("AUTO_DELIVER", True)),
        "PAYWAY_ENABLED": bool(s.get("PAYWAY_MERCHANT_ID") and s.get("PAYWAY_API_KEY")),
        "PAYWAY_SANDBOX": bool(s.get("PAYWAY_SANDBOX", True)),
        "KHMER_ENABLED": bool(s.get("KHMER_SECRET_KEY")),
    }


def _fulfill_order(d, order):
    """Decrease stock + deliver key/file. Mutates order and d."""
    product_id = order.get("product_id")
    product = next((p for p in d["products"] if p["id"] == product_id), None)
    if product and int(product.get("stock", 0)) > 0:
        product["stock"] = int(product["stock"]) - 1
    delivery, delivery_file = _pop_stock_item(d, product_id)
    order["delivery"] = delivery
    order["delivery_file"] = delivery_file
    order["status"] = "paid" if (delivery or delivery_file) else "waiting_confirm"
    order["paid_at"] = utc_now()
    return order


@app.route("/api/order", methods=["POST"])
def create_order():
    """Create order in pending_payment — deliver after user confirms paid."""
    body = request.get_json(force=True, silent=True) or {}
    product_id = body.get("product_id")
    buyer = (body.get("telegram") or body.get("contact") or "").strip()
    note = (body.get("note") or "").strip()

    if not buyer:
        return jsonify({"ok": False, "error": "សូមបញ្ចូល Telegram / Contact"}), 400

    d = db_read()
    product = next((p for p in d["products"] if p["id"] == product_id and p.get("active", True)), None)
    if not product:
        return jsonify({"ok": False, "error": "Product មិនមាន"}), 404
    if int(product.get("stock", 0)) <= 0:
        return jsonify({"ok": False, "error": "អស់ stock"}), 400

    order_id = f"SK{d.get('next_order', 1001)}"
    d["next_order"] = int(d.get("next_order", 1001)) + 1

    order = {
        "id": order_id,
        "product_id": product_id,
        "product_name": product["name"],
        "price": float(product["price"]),
        "buyer": buyer,
        "note": note,
        "status": "pending_payment",
        "delivery": None,
        "delivery_file": None,
        "created_at": utc_now(),
        "paid_at": None,
    }
    d.setdefault("orders", []).insert(0, order)

    pay = _payment_info(d)
    payway_qr = None
    s = d.get("settings") or {}

    # --- KHMER SYSTEM (preferred when configured) ---
    ks_secret = (s.get("KHMER_SECRET_KEY") or "").strip()
    if ks_secret:
        try:
            vkey = khmer_system.make_verify_key()
            # API requires telegram_user_id — use digits from contact or hash
            tg_raw = buyer.lstrip("@")
            tg_id = "".join(c for c in tg_raw if c.isdigit()) or str(abs(hash(tg_raw)) % 10**9)
            resp = khmer_system.generate(
                secret_key=ks_secret,
                amount=float(product["price"]),
                verify_key=vkey,
                telegram_user_id=tg_id,
                bakong_account_id=(s.get("BAKONG_ID") or None) or None,
                merchant_name=(s.get("SHOP_NAME") or s.get("SITE_NAME") or "Sina Key"),
            )
            if resp.get("success") and (resp.get("qr_image_url") or resp.get("qr_string")):
                order["ks_verify_key"] = vkey
                order["ks_telegram_user_id"] = tg_id
                order["ks_transaction_id"] = resp.get("transaction_id")
                pay["PAYMENT_QR"] = resp.get("qr_image_url") or ""
                pay["KS_DYNAMIC"] = True
                pay["KS_QR_STRING"] = resp.get("qr_string") or ""
                pay["PAYMENT_NOTE"] = "ស្កេន KHQR (ABA / ធនាគារណាមួយ) · auto verify"
            else:
                order["ks_error"] = resp.get("error") or resp.get("code") or str(resp)[:200]
        except Exception as e:
            order["ks_error"] = str(e)

    mid = (s.get("PAYWAY_MERCHANT_ID") or "").strip()
    key = (s.get("PAYWAY_API_KEY") or "").strip()
    # ABA PayWay only if Khmer System not used
    if not order.get("ks_verify_key") and mid and key:
        # ABA PayWay dynamic QR
        try:
            base = request.url_root.rstrip("/")
            cb = base + "/api/payway/callback"
            resp = payway.generate_qr(
                merchant_id=mid,
                api_key=key,
                tran_id=order_id.replace("SK", "T")[:20],
                amount=float(product["price"]),
                currency=s.get("CURRENCY") or "USD",
                sandbox=bool(s.get("PAYWAY_SANDBOX", True)),
                callback_url=cb,
                first_name="Customer",
                last_name="Sina",
                phone="",
                items_name=product["name"],
                lifetime=30,
            )
            st = (resp.get("status") or {})
            code = str(st.get("code", ""))
            if code in ("0", "00") or resp.get("qrImage"):
                payway_qr = {
                    "qrImage": resp.get("qrImage") or "",
                    "qrString": resp.get("qrString") or "",
                    "deeplink": resp.get("abapay_deeplink") or "",
                    "tran_id": order_id.replace("SK", "T")[:20],
                }
                order["payway_tran_id"] = payway_qr["tran_id"]
                if payway_qr["qrImage"]:
                    pay["PAYMENT_QR"] = payway_qr["qrImage"]
                    pay["PAYWAY_DYNAMIC"] = True
                    pay["PAYWAY_DEEPLINK"] = payway_qr["deeplink"]
            else:
                order["payway_error"] = st.get("message") or str(resp)[:200]
        except Exception as e:
            order["payway_error"] = str(e)

    # --- KHMER SYSTEM (pay.khmer-system.com) ---
    ks_secret = (s.get("KHMER_SECRET_KEY") or "").strip()
    ks_data = None
    if ks_secret and not payway_qr:
        try:
            vkey = khmer_system.make_verify_key()
            # telegram id: digits from buyer, or hash fallback for web users
            tg_id = "".join(c for c in buyer if c.isdigit()) or str(abs(hash(buyer)) % 10**9)
            gen = khmer_system.generate(
                secret_key=ks_secret,
                amount=float(product["price"]),
                verify_key=vkey,
                telegram_user_id=tg_id,
                bakong_account_id=(s.get("BAKONG_ID") or None) or None,
                merchant_name=(s.get("SHOP_NAME") or s.get("SITE_NAME") or "Sina Key"),
            )
            if gen.get("success") and (gen.get("qr_image_url") or gen.get("qr_string")):
                order["ks_verify_key"] = vkey
                order["ks_telegram_id"] = tg_id
                order["ks_transaction_id"] = gen.get("transaction_id")
                pay["PAYMENT_QR"] = gen.get("qr_image_url") or ""
                pay["KHMER_SYSTEM"] = True
                pay["KS_VERIFY_KEY"] = vkey
                ks_data = {
                    "qr_image_url": gen.get("qr_image_url"),
                    "qr_string": gen.get("qr_string"),
                    "transaction_id": gen.get("transaction_id"),
                    "verify_key": vkey,
                    "expired_at": gen.get("expired_at"),
                }
            else:
                order["ks_error"] = gen.get("error") or gen.get("code") or str(gen)[:200]
        except Exception as e:
            order["ks_error"] = str(e)

    db_write(d)
    msg = "សូមស្កេន KHQR បង់ប្រាក់"
    if payway_qr:
        msg = "សូមស្កេន ABA KHQR បង់ប្រាក់"
    elif ks_data:
        msg = "សូមស្កេន KHQR (Khmer System) បង់ប្រាក់"
    return jsonify({
        "ok": True,
        "order": order,
        "payment": pay,
        "payway": payway_qr,
        "khmer_system": ks_data,
        "message": msg,
    })


@app.route("/api/order/check-payment", methods=["POST"])
def check_payment():
    """Poll Khmer System or ABA PayWay until paid, then fulfill."""
    body = request.get_json(force=True, silent=True) or {}
    oid = (body.get("order_id") or body.get("id") or "").strip().upper()
    if not oid:
        return jsonify({"ok": False, "error": "Missing order_id"}), 400
    d = db_read()
    order = next((o for o in d.get("orders", []) if str(o.get("id", "")).upper() == oid), None)
    if not order:
        return jsonify({"ok": False, "error": "Order not found"}), 404
    if order.get("status") in ("paid", "delivered"):
        return jsonify({"ok": True, "order": order, "payment_status": "completed", "message": "Paid"})

    s = d.get("settings") or {}

    # Khmer System
    if order.get("ks_verify_key") and (s.get("KHMER_SECRET_KEY") or "").strip():
        resp = khmer_system.check(
            secret_key=s["KHMER_SECRET_KEY"].strip(),
            verify_key=order["ks_verify_key"],
            telegram_user_id=order.get("ks_telegram_user_id") or "0",
        )
        st = (resp.get("status") or "").lower()
        if st == "completed":
            _fulfill_order(d, order)
            # confirm credit (best-effort)
            try:
                khmer_system.confirm(
                    secret_key=s["KHMER_SECRET_KEY"].strip(),
                    verify_key=order["ks_verify_key"],
                    telegram_user_id=order.get("ks_telegram_user_id") or "0",
                )
            except Exception:
                pass
            db_write(d)
            return jsonify({"ok": True, "order": order, "payment_status": "completed", "message": "បង់រួច — deliver"})
        if st == "expired":
            order["status"] = "expired"
            db_write(d)
            return jsonify({"ok": True, "order": order, "payment_status": "expired", "message": "QR ផុតកំណត់"})
        return jsonify({"ok": True, "order": order, "payment_status": st or "pending", "message": "រង់ចាំបង់ប្រាក់"})

    # fallback ABA PayWay
    mid = (s.get("PAYWAY_MERCHANT_ID") or "").strip()
    key = (s.get("PAYWAY_API_KEY") or "").strip()
    if mid and key and order.get("payway_tran_id"):
        resp = payway.check_transaction(
            merchant_id=mid, api_key=key, tran_id=order["payway_tran_id"],
            sandbox=bool(s.get("PAYWAY_SANDBOX", True)),
        )
        data = resp.get("data") or {}
        status = (data.get("payment_status") or "").upper()
        if status in ("APPROVED", "PRE-AUTH") or data.get("payment_status_code") == 0:
            _fulfill_order(d, order)
            db_write(d)
            return jsonify({"ok": True, "order": order, "payment_status": "completed", "message": "បង់រួច — deliver"})
        return jsonify({"ok": True, "order": order, "payment_status": status or "PENDING", "message": "រង់ចាំបង់ប្រាក់"})

    return jsonify({"ok": True, "order": order, "payment_status": "pending", "message": "រង់ចាំបង់ / confirm"})


@app.route("/api/order/check-payway", methods=["POST"])
def check_payway():
    """Poll ABA PayWay transaction status; auto-fulfill if APPROVED."""
    body = request.get_json(force=True, silent=True) or {}
    oid = (body.get("order_id") or body.get("id") or "").strip().upper()
    if not oid:
        return jsonify({"ok": False, "error": "Missing order_id"}), 400
    d = db_read()
    order = next((o for o in d.get("orders", []) if str(o.get("id", "")).upper() == oid), None)
    if not order:
        return jsonify({"ok": False, "error": "Order not found"}), 404
    if order.get("status") in ("paid", "delivered"):
        return jsonify({"ok": True, "order": order, "payment_status": "APPROVED", "message": "Paid"})

    s = d.get("settings") or {}
    mid = (s.get("PAYWAY_MERCHANT_ID") or "").strip()
    key = (s.get("PAYWAY_API_KEY") or "").strip()
    if not mid or not key:
        return jsonify({"ok": False, "error": "PayWay not configured"}), 400
    tran_id = order.get("payway_tran_id") or oid.replace("SK", "T")[:20]
    resp = payway.check_transaction(
        merchant_id=mid,
        api_key=key,
        tran_id=tran_id,
        sandbox=bool(s.get("PAYWAY_SANDBOX", True)),
    )
    data = resp.get("data") or {}
    status = (data.get("payment_status") or "").upper()
    if status in ("APPROVED", "PRE-AUTH") or data.get("payment_status_code") == 0:
        _fulfill_order(d, order)
        db_write(d)
        return jsonify({"ok": True, "order": order, "payment_status": status or "APPROVED", "message": "បង់រួច — deliver"})
    return jsonify({
        "ok": True,
        "order": order,
        "payment_status": status or "PENDING",
        "message": "រង់ចាំបង់ប្រាក់" if status in ("", "PENDING") else status,
        "raw": {"code": (resp.get("status") or {}).get("code"), "msg": (resp.get("status") or {}).get("message")},
    })


@app.route("/api/order/check-ks", methods=["POST"])
def check_ks():
    """Poll KHMER SYSTEM payment status; fulfill on completed."""
    body = request.get_json(force=True, silent=True) or {}
    oid = (body.get("order_id") or body.get("id") or "").strip().upper()
    if not oid:
        return jsonify({"ok": False, "error": "Missing order_id"}), 400
    d = db_read()
    order = next((o for o in d.get("orders", []) if str(o.get("id", "")).upper() == oid), None)
    if not order:
        return jsonify({"ok": False, "error": "Order not found"}), 404
    if order.get("status") in ("paid", "delivered"):
        return jsonify({"ok": True, "order": order, "payment_status": "completed", "message": "Paid"})

    s = d.get("settings") or {}
    secret = (s.get("KHMER_SECRET_KEY") or "").strip()
    vkey = order.get("ks_verify_key")
    tg_id = order.get("ks_telegram_id")
    if not secret or not vkey or not tg_id:
        return jsonify({"ok": False, "error": "Khmer System not configured for this order"}), 400

    resp = khmer_system.check(secret, vkey, tg_id)
    status = (resp.get("status") or "").lower()
    if status == "completed":
        _fulfill_order(d, order)
        try:
            khmer_system.confirm(secret, vkey, tg_id)
        except Exception:
            pass
        db_write(d)
        return jsonify({"ok": True, "order": order, "payment_status": "completed", "message": "បង់រួច — deliver"})
    if status == "expired":
        order["status"] = "expired"
        db_write(d)
        return jsonify({"ok": True, "order": order, "payment_status": "expired", "message": "QR ផុតកំណត់"})
    return jsonify({
        "ok": True,
        "order": order,
        "payment_status": status or "pending",
        "message": "រង់ចាំបង់ប្រាក់",
    })


@app.route("/api/payway/callback", methods=["POST", "GET"])
def payway_callback():
    """ABA PayWay payment notification (return_url / callback)."""
    body = {}
    if request.method == "POST":
        body = request.get_json(force=True, silent=True) or {}
        if not body:
            body = request.form.to_dict() if request.form else {}
    else:
        body = request.args.to_dict()

    # Common fields vary; try several
    tran_id = (
        body.get("tran_id")
        or body.get("transaction_id")
        or (body.get("data") or {}).get("tran_id")
        or ""
    )
    status = (
        body.get("payment_status")
        or body.get("status")
        or (body.get("data") or {}).get("payment_status")
        or ""
    )
    if isinstance(status, dict):
        status = status.get("message") or status.get("code") or ""

    d = db_read()
    order = None
    if tran_id:
        order = next(
            (o for o in d.get("orders", []) if o.get("payway_tran_id") == tran_id or o.get("id", "").replace("SK", "T")[:20] == tran_id),
            None,
        )
    if order and order.get("status") not in ("paid", "delivered"):
        st = str(status).upper()
        if st in ("APPROVED", "0", "00", "SUCCESS", "PAID") or body.get("payment_status_code") == 0:
            _fulfill_order(d, order)
            order["payway_callback"] = True
            db_write(d)

    return jsonify({"ok": True})


@app.route("/api/order/confirm-paid", methods=["POST"])
def confirm_paid():
    """User confirms they paid via KHQR — auto-deliver if enabled + stock."""
    body = request.get_json(force=True, silent=True) or {}
    oid = (body.get("order_id") or body.get("id") or "").strip().upper()
    if not oid:
        return jsonify({"ok": False, "error": "Missing order_id"}), 400

    d = db_read()
    order = next((o for o in d.get("orders", []) if str(o.get("id", "")).upper() == oid), None)
    if not order:
        return jsonify({"ok": False, "error": "រកមិនឃើញ order"}), 404
    if order.get("status") in ("paid", "delivered"):
        return jsonify({"ok": True, "order": order, "message": "Order បាន deliver រួច"})
    if order.get("status") not in ("pending_payment", "waiting_confirm", "pending"):
        return jsonify({"ok": False, "error": "Status មិនអនុញ្ញាត"}), 400

    s = d.get("settings") or {}
    auto = bool(s.get("AUTO_DELIVER", True))

    # If PayWay configured, verify with ABA first
    mid = (s.get("PAYWAY_MERCHANT_ID") or "").strip()
    key = (s.get("PAYWAY_API_KEY") or "").strip()
    if mid and key and order.get("payway_tran_id"):
        resp = payway.check_transaction(
            merchant_id=mid,
            api_key=key,
            tran_id=order["payway_tran_id"],
            sandbox=bool(s.get("PAYWAY_SANDBOX", True)),
        )
        data = resp.get("data") or {}
        st = (data.get("payment_status") or "").upper()
        if st not in ("APPROVED", "PRE-AUTH") and data.get("payment_status_code") != 0:
            return jsonify({
                "ok": False,
                "error": "ABA មិនទាន់ទទួលប្រាក់ (status=" + (st or "PENDING") + ")",
                "payment_status": st or "PENDING",
            }), 402

    if auto:
        _fulfill_order(d, order)
        msg = "បង់រួច — file/key រួចរាល់" if (order.get("delivery") or order.get("delivery_file")) else "បង់រួច — រង់ចាំ admin ផ្ញើ key"
    else:
        order["status"] = "waiting_confirm"
        order["paid_at"] = utc_now()
        msg = "បានជូនដំណឹង admin — រង់ចាំផ្ទៀងផ្ទាត់"

    db_write(d)
    return jsonify({"ok": True, "order": order, "message": msg})


@app.route("/api/track")
def track_order():
    oid = (request.args.get("id") or "").strip().upper()
    if not oid:
        return jsonify({"ok": False, "error": "Missing order id"}), 400
    d = db_read()
    order = next((o for o in d.get("orders", []) if str(o.get("id", "")).upper() == oid), None)
    if not order:
        return jsonify({"ok": False, "error": "រកមិនឃើញ order"}), 404
    # hide internal fields for public
    show = order.get("status") in ("paid", "delivered")
    # also return payment info for unpaid orders

    public = {
        "id": order["id"],
        "product_name": order.get("product_name"),
        "price": order.get("price"),
        "status": order.get("status"),
        "delivery": order.get("delivery") if show else None,
        "delivery_file": order.get("delivery_file") if show else None,
        "download_url": (f"/api/download/{order['id']}") if show and order.get("delivery_file") else None,
        "created_at": order.get("created_at"),
        "paid_at": order.get("paid_at"),
    }
    pay = _payment_info(d) if order.get("status") in ("pending_payment", "waiting_confirm") else None
    return jsonify({"ok": True, "order": public, "payment": pay})


# ---------- Admin API ----------
@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    body = request.get_json(force=True, silent=True) or {}
    pw = body.get("password") or ""
    d = db_read()
    expected = d.get("settings", {}).get("ADMIN_PASSWORD", "admin123")
    if pw == expected or pw == os.environ.get("ADMIN_PASSWORD", ""):
        session["admin"] = True
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "ពាក្យសម្ងាត់មិនត្រឹមត្រូវ"}), 401


@app.route("/api/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin", None)
    return jsonify({"ok": True})


@app.route("/api/admin/me")
def admin_me():
    return jsonify({"ok": True, "admin": bool(session.get("admin"))})


@app.route("/api/admin/data")
@admin_required
def admin_data():
    d = db_read()
    return jsonify({
        "ok": True,
        "settings": d.get("settings", {}),
        "categories": d.get("categories", []),
        "products": d.get("products", []),
        "orders": d.get("orders", [])[:100],
        "stock_files": {k: len(v) if isinstance(v, list) else 0 for k, v in (d.get("stock_files") or {}).items()},
    })


@app.route("/api/admin/product", methods=["POST", "PUT", "DELETE"])
@admin_required
def admin_product():
    d = db_read()
    body = request.get_json(force=True, silent=True) or {}

    if request.method == "DELETE":
        pid = body.get("id")
        d["products"] = [p for p in d["products"] if p["id"] != pid]
        db_write(d)
        return jsonify({"ok": True})

    if request.method == "POST":
        new_id = max([p["id"] for p in d["products"]] or [0]) + 1
        product = {
            "id": new_id,
            "cat": body.get("cat") or "mode",
            "name": (body.get("name") or "New Product").strip(),
            "desc": (body.get("desc") or "").strip(),
            "price": float(body.get("price") or 0),
            "stock": int(body.get("stock") or 0),
            "badge": (body.get("badge") or "").strip(),
            "image": (body.get("image") or "").strip(),
            "duration": (body.get("duration") or "").strip(),
            "active": bool(body.get("active", True)),
        }
        d["products"].append(product)
        db_write(d)
        return jsonify({"ok": True, "product": product})

    # PUT
    pid = body.get("id")
    for p in d["products"]:
        if p["id"] == pid:
            for k in ("cat", "name", "desc", "badge", "image", "duration"):
                if k in body:
                    p[k] = body[k]
            if "price" in body:
                p["price"] = float(body["price"])
            if "stock" in body:
                p["stock"] = int(body["stock"])
            if "active" in body:
                p["active"] = bool(body["active"])
            db_write(d)
            return jsonify({"ok": True, "product": p})
    return jsonify({"ok": False, "error": "Not found"}), 404


@app.route("/api/admin/stock", methods=["GET", "POST", "DELETE"])
@admin_required
def admin_stock():
    """List / add text keys / delete stock for a product."""
    d = db_read()
    stock = d.setdefault("stock_files", {})

    if request.method == "GET":
        pid = str(request.args.get("product_id") or "")
        if not pid:
            # summary
            summary = {}
            for k, v in stock.items():
                items = v if isinstance(v, list) else []
                summary[k] = {
                    "count": len(items),
                    "files": sum(1 for x in items if isinstance(x, dict) and x.get("type") == "file"),
                    "texts": sum(1 for x in items if not (isinstance(x, dict) and x.get("type") == "file")),
                }
            return jsonify({"ok": True, "summary": summary})
        items = stock.get(pid) or []
        listed = []
        for i, raw in enumerate(items):
            it = normalize_stock_item(raw)
            listed.append({
                "index": i,
                "type": it.get("type", "text"),
                "label": stock_label(it),
                "name": it.get("name"),
                "path": it.get("path"),
            })
        return jsonify({"ok": True, "product_id": pid, "items": listed, "count": len(listed)})

    if request.method == "DELETE":
        body = request.get_json(force=True, silent=True) or {}
        pid = str(body.get("product_id") or "")
        idx = body.get("index")
        if pid == "" or idx is None:
            return jsonify({"ok": False, "error": "product_id + index required"}), 400
        cur = stock.get(pid) or []
        if not isinstance(cur, list) or idx < 0 or idx >= len(cur):
            return jsonify({"ok": False, "error": "invalid index"}), 400
        removed = cur.pop(idx)
        # try delete file from disk
        it = normalize_stock_item(removed)
        if it.get("type") == "file" and it.get("path"):
            fp = UPLOAD_DIR / it["path"]
            try:
                if fp.exists():
                    fp.unlink()
            except OSError:
                pass
        stock[pid] = cur
        for p in d["products"]:
            if str(p["id"]) == pid:
                p["stock"] = len(cur)
                break
        d["stock_files"] = stock
        db_write(d)
        return jsonify({"ok": True, "count": len(cur)})

    # POST — text lines
    body = request.get_json(force=True, silent=True) or {}
    pid = str(body.get("product_id") or "")
    lines = body.get("lines") or body.get("text") or ""
    if isinstance(lines, str):
        items = [x.strip() for x in lines.splitlines() if x.strip()]
    else:
        items = [str(x).strip() for x in lines if str(x).strip()]
    if not pid or not items:
        return jsonify({"ok": False, "error": "product_id + lines required"}), 400

    cur = stock.get(pid) or []
    if not isinstance(cur, list):
        cur = []
    for line in items:
        cur.append({"type": "text", "value": line})
    stock[pid] = cur
    for p in d["products"]:
        if str(p["id"]) == pid:
            p["stock"] = len(cur)
            break
    d["stock_files"] = stock
    db_write(d)
    return jsonify({"ok": True, "count": len(cur)})


@app.route("/api/admin/upload", methods=["POST"])
@admin_required
def admin_upload():
    """Upload one or more Mode/DNS/Key files for a product."""
    pid = str(request.form.get("product_id") or request.args.get("product_id") or "")
    if not pid:
        return jsonify({"ok": False, "error": "product_id required"}), 400

    files = request.files.getlist("files") or request.files.getlist("file")
    if not files:
        single = request.files.get("file")
        files = [single] if single else []
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({"ok": False, "error": "No files uploaded"}), 400

    dest_dir = UPLOAD_DIR / pid
    dest_dir.mkdir(parents=True, exist_ok=True)

    d = db_read()
    stock = d.setdefault("stock_files", {})
    cur = stock.get(pid) or []
    if not isinstance(cur, list):
        cur = []

    saved = []
    for f in files:
        name = secure_filename(f.filename) or f"file_{secrets.token_hex(4)}"
        if not allowed_file(name):
            return jsonify({"ok": False, "error": f"File type not allowed: {name}"}), 400
        unique = f"{secrets.token_hex(8)}_{name}"
        rel = f"{pid}/{unique}"
        path = UPLOAD_DIR / rel
        f.save(path)
        entry = {"type": "file", "name": name, "path": rel, "size": path.stat().st_size}
        cur.append(entry)
        saved.append({"name": name, "path": rel, "size": entry["size"]})

    stock[pid] = cur
    for p in d["products"]:
        if str(p["id"]) == pid:
            p["stock"] = len(cur)
            break
    d["stock_files"] = stock
    db_write(d)
    return jsonify({"ok": True, "count": len(cur), "uploaded": saved})


@app.route("/api/download/<order_id>")
def download_order_file(order_id):
    """Buyer download for delivered file stock."""
    d = db_read()
    order = next((o for o in d.get("orders", []) if str(o.get("id", "")).upper() == order_id.upper()), None)
    if not order:
        return jsonify({"ok": False, "error": "Order not found"}), 404
    if order.get("status") not in ("paid", "delivered"):
        return jsonify({"ok": False, "error": "Order not ready"}), 403
    df = order.get("delivery_file") or {}
    rel = df.get("path")
    if not rel:
        return jsonify({"ok": False, "error": "No file on this order"}), 404
    path = UPLOAD_DIR / rel
    if not path.exists():
        return jsonify({"ok": False, "error": "File missing on server"}), 404
    return send_file(path, as_attachment=True, download_name=df.get("name") or path.name)


@app.route("/api/admin/order", methods=["PATCH"])
@admin_required
def admin_order_patch():
    body = request.get_json(force=True, silent=True) or {}
    oid = body.get("id")
    d = db_read()
    for o in d.get("orders", []):
        if o["id"] == oid:
            if "status" in body:
                o["status"] = body["status"]
            if "delivery" in body:
                o["delivery"] = body["delivery"]
            db_write(d)
            return jsonify({"ok": True, "order": o})
    return jsonify({"ok": False, "error": "Not found"}), 404


@app.route("/api/admin/settings", methods=["PUT"])
@admin_required
def admin_settings():
    body = request.get_json(force=True, silent=True) or {}
    d = db_read()
    s = d.setdefault("settings", {})
    for k in (
        "SITE_NAME", "SITE_TAGLINE", "TELEGRAM", "CONTACT_NOTE", "ADMIN_PASSWORD",
        "PAYMENT_QR", "BAKONG_ID", "SHOP_NAME", "PAYMENT_NOTE", "AUTO_DELIVER",
        "PAYWAY_MERCHANT_ID", "PAYWAY_API_KEY", "PAYWAY_SANDBOX", "CURRENCY", "KHMER_SECRET_KEY", "KHMER_SECRET_KEY",
    ):
        if k in body and body[k] is not None:
            if k in ("AUTO_DELIVER", "PAYWAY_SANDBOX"):
                s[k] = bool(body[k]) if not isinstance(body[k], str) else body[k] in ("1", "true", "True", True)
            else:
                s[k] = body[k]
    db_write(d)
    return jsonify({"ok": True, "settings": s})


@app.route("/api/admin/upload-product-image", methods=["POST"])
@admin_required
def admin_upload_product_image():
    """Upload image for a product; optionally attach to product_id."""
    f = request.files.get("file") or request.files.get("image")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "No image"}), 400
    name = secure_filename(f.filename) or "product.png"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else "png"
    if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
        return jsonify({"ok": False, "error": "Must be image"}), 400
    pid = str(request.form.get("product_id") or "").strip()
    unique = f"product_{pid or secrets.token_hex(4)}_{secrets.token_hex(4)}.{ext}"
    path = UPLOAD_DIR / unique
    f.save(path)
    url = f"/api/media/{unique}"
    if pid.isdigit():
        d = db_read()
        for prod in d.get("products", []):
            if prod["id"] == int(pid):
                prod["image"] = url
                break
        db_write(d)
    return jsonify({"ok": True, "url": url, "product_id": int(pid) if pid.isdigit() else None})


@app.route("/api/admin/upload-qr", methods=["POST"])
@admin_required
def admin_upload_qr():
    """Upload KHQR / Bakong payment QR image."""
    f = request.files.get("file") or request.files.get("qr")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "No QR file"}), 400
    name = secure_filename(f.filename) or "qr.png"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else "png"
    if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
        return jsonify({"ok": False, "error": "QR must be image"}), 400
    rel = f"payment_qr.{ext}"
    path = UPLOAD_DIR / rel
    f.save(path)
    url = f"/api/media/{rel}"
    d = db_read()
    s = d.setdefault("settings", {})
    s["PAYMENT_QR"] = url
    db_write(d)
    return jsonify({"ok": True, "url": url})


@app.route("/api/media/<path:filename>")
def media_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
