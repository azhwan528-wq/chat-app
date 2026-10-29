from aiohttp import web, WSMsgType
import sqlite3
import json
import os
import random
import string
from datetime import datetime, timedelta
from urllib.parse import unquote
import aiosmtplib
from email.message import EmailMessage

DB = os.path.join(os.path.dirname(__file__), "chat.db")
HTML = os.path.join(os.path.dirname(__file__), "index.html")

# ---------- تنظیمات ایمیل (از Environment Variables) ----------
EMAIL_USER = os.environ.get("EMAIL_USER", "")
EMAIL_PASS = os.environ.get("EMAIL_PASS", "")
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# ---------- دیتابیس ----------
def init_db():
    conn = sqlite3.connect(DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            phone TEXT,
            verified INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            email TEXT PRIMARY KEY,
            code TEXT,
            expires_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            text TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_user(email, phone):
    conn = sqlite3.connect(DB)
    conn.execute(
        "INSERT OR REPLACE INTO users (email, phone, verified, created_at) VALUES (?, ?, 0, ?)",
        (email, phone, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def set_verified(email):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE users SET verified=1 WHERE email=?", (email,))
    conn.commit()
    conn.close()

def is_verified(email):
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT verified FROM users WHERE email=?", (email,)).fetchone()
    conn.close()
    return bool(row and row[0])

def save_code(email, code):
    conn = sqlite3.connect(DB)
    expires = (datetime.now() + timedelta(minutes=10)).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO codes (email, code, expires_at) VALUES (?, ?, ?)",
        (email, code, expires)
    )
    conn.commit()
    conn.close()

def check_code(email, code):
    conn = sqlite3.connect(DB)
    row = conn.execute(
        "SELECT code, expires_at FROM codes WHERE email=?", (email,)
    ).fetchone()
    conn.close()
    if not row:
        return False
    saved_code, expires_at = row
    if datetime.fromisoformat(expires_at) < datetime.now():
        return False
    return saved_code == code

def save_message(username, text):
    conn = sqlite3.connect(DB)
    conn.execute(
        "INSERT INTO messages (username, text, timestamp) VALUES (?, ?, ?)",
        (username, text, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_history(limit=50):
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT username, text, timestamp FROM messages ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return list(reversed(rows))

init_db()

# ---------- ارسال ایمیل ----------
async def send_email(to_email, code):
    if not EMAIL_USER or not EMAIL_PASS:
        print("⚠️ EMAIL_USER یا EMAIL_PASS تنظیم نشده!")
        return False
    try:
        msg = EmailMessage()
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        msg["Subject"] = "کد تأیید چت"
        msg.set_content(f"""
سلام! 👋

کد تأیید شما برای ورود به چت:

    {code}

این کد ۱۰ دقیقه اعتبار داره.

اگه شما این درخواست رو ندادی، نادیده بگیر.
""")
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            start_tls=True,
            username=EMAIL_USER,
            password=EMAIL_PASS,
        )
        print(f"✅ ایمیل به {to_email} فرستاده شد")
        return True
    except Exception as e:
        print(f"❌ خطا در ارسال ایمیل: {e}")
        return False

# ---------- WebSocket management ----------
sockets = set()

async def broadcast(message):
    if not sockets:
        return
    data = json.dumps(message, ensure_ascii=False)
    dead = []
    for ws, _ in list(sockets):
        try:
            await ws.send_str(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        for item in list(sockets):
            if item[0] is ws:
                sockets.discard(item)

# ---------- Routes ----------
async def index(request):
    return web.FileResponse(HTML)

async def api_send_code(request):
    try:
        data = await request.json()
        email = data.get("email", "").strip().lower()
        phone = data.get("phone", "").strip()

        if not email or "@" not in email:
            return web.json_response({"ok": False, "error": "ایمیل معتبر نیست"}, status=400)
        if not phone or len(phone) < 10:
            return web.json_response({"ok": False, "error": "شماره موبایل معتبر نیست"}, status=400)

        save_user(email, phone)

        # کد ۶ رقمی تصادفی
        code = "".join(random.choices(string.digits, k=6))
        save_code(email, code)

        sent = await send_email(email, code)
        if not sent:
            return web.json_response({"ok": False, "error": "خطا در ارسال ایمیل"}, status=500)

        return web.json_response({"ok": True, "message": "کد فرستاده شد"})
    except Exception as e:
        print(f"❌ خطا در send_code: {e}")
        return web.json_response({"ok": False, "error": "خطای سرور"}, status=500)

async def api_verify_code(request):
    try:
        data = await request.json()
        email = data.get("email", "").strip().lower()
        code = data.get("code", "").strip()

        if not email or not code:
            return web.json_response({"ok": False, "error": "اطلاعات ناقص"}, status=400)

        if check_code(email, code):
            set_verified(email)
            return web.json_response({"ok": True, "message": "تأیید شد"})
        else:
            return web.json_response({"ok": False, "error": "کد اشتباه یا منقضی"}, status=400)
    except Exception as e:
        print(f"❌ خطا در verify_code: {e}")
        return web.json_response({"ok": False, "error": "خطای سرور"}, status=500)

# ---------- WebSocket ----------
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    username = unquote(request.match_info["username"]) or "ناشناس"
    sockets.add((ws, username))

    for u, t, ts in get_history():
        await ws.send_str(json.dumps(
            {"type": "message", "username": u, "text": t, "timestamp": ts},
            ensure_ascii=False
        ))

    await broadcast({"type": "system", "text": f"🟢 {username} وارد شد"})

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                text = msg.data
                save_message(username, text)
                await broadcast({
                    "type": "message",
                    "username": username,
                    "text": text,
                    "timestamp": datetime.now().isoformat()
                })
            elif msg.type == WSMsgType.ERROR:
                break
    finally:
        sockets.discard((ws, username))
        await broadcast({"type": "system", "text": f"🔴 {username} خارج شد"})

    return ws

# ---------- App ----------
app = web.Application()
app.router.add_get("/", index)
app.router.add_post("/api/send_code", api_send_code)
app.router.add_post("/api/verify_code", api_verify_code)
app.router.add_get("/ws/{username}", websocket_handler)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"✅ سرور روی پورت {port} اجرا شد")
    print(f"📧 EMAIL_USER: {'✅ تنظیم شده' if EMAIL_USER else '❌ تنظیم نشده'}")
    web.run_app(app, host="0.0.0.0", port=port, print=None)
