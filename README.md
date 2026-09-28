# Sina Key — Mode / DNS / Key Shop

Flask shop with **KHMER SYSTEM auto payment** (KHQR).

## Payment flow
1. Customer orders → server calls `POST pay.khmer-system.com/api/v1/payment/generate`
2. Dynamic KHQR shown (ABA / any Bakong bank)
3. Frontend polls `/api/order/check-payment` every ~4s
4. On `completed` → auto deliver key/file + `confirm` credit

## Setup Khmer System
1. Register: https://khmer-system.com
2. Get `sk_live_...` secret key
3. `/admin` → Settings → **KHMER SYSTEM Secret Key** → Save
4. Optional: Bakong Account ID, Shop name

## Run
```bash
pip install -r requirements.txt
python app.py
# http://127.0.0.1:5000
```

## Render
Web Service + Disk `/var/data` · see `render.yaml`
