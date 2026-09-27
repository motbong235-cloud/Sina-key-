# Sina Key — Website (HTML + Flask)

Website លក់ **Key · DNS · Mode File**  
UI = **HTML** (`templates/`) · Server = Python (សម្រាប់ upload / order)

> Render **Web Service** (មិនមែន Static Site) — ព្រោះត្រូវ upload file + order API

---

## Deploy លើ Render (Web Service)

1. Upload folder នេះទៅ **GitHub**
2. [Render Dashboard](https://dashboard.render.com) → **New** → **Web Service**
3. Connect repo
4. កំណត់:

| Field | Value |
|--------|--------|
| **Runtime** | Python |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60` |
| **Plan** | Starter (ត្រូវ Disk) |

5. **Environment**
   - `ADMIN_PASSWORD` = ពាក្យសម្ងាត់ admin របស់អ្នក
   - `SECRET_KEY` = random (ឬ Generate)
   - `DATA_DIR` = `/var/data`

6. **Disk** (សំខាន់!)
   - Name: `sina-key-data`
   - Mount path: `/var/data`
   - Size: 1 GB

7. Deploy → បើក URL របស់ Render

- Shop: `https://your-service.onrender.com/`
- Admin: `https://your-service.onrender.com/admin`

---

## Files (HTML នៅទីនេះ)

```
sina-key/
├── templates/
│   ├── index.html    ← ទំព័រ Shop (HTML)
│   └── admin.html    ← Admin panel (HTML)
├── app.py            ← Web server
├── requirements.txt
├── Procfile
├── render.yaml
└── data/db.json
```

---

## Run local

```bash
pip install -r requirements.txt
python app.py
```

- http://127.0.0.1:5000  
- http://127.0.0.1:5000/admin  
- Password ដើម: `admin123`
