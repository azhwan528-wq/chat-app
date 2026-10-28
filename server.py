from aiohttp import web, WSMsgType
import sqlite3
import json
import os
from datetime import datetime
from urllib.parse import unquote

DB = os.path.join(os.path.dirname(__file__), "chat.db")
HTML = os.path.join(os.path.dirname(__file__), "index.html")

# ---------- دیتابیس ----------
def init_db():
    conn = sqlite3.connect(DB)
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

# ---------- مدیریت اتصال ----------
sockets = set()  # هر آیتم: (ws, username)

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
        # حذف امن
        for item in list(sockets):
            if item[0] is ws:
                sockets.discard(item)

# ---------- صفحه اصلی ----------
async def index(request):
    return web.FileResponse(HTML)

# ---------- WebSocket ----------
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    username = unquote(request.match_info["username"]) or "ناشناس"
    sockets.add((ws, username))

    # تاریخچه برای کاربر جدید
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

# ---------- راه‌اندازی ----------
app = web.Application()
app.router.add_get("/", index)
app.router.add_get("/ws/{username}", websocket_handler)

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"✅ سرور روی پورت {port} اجرا شد")
    web.run_app(app, host="0.0.0.0", port=port, print=None)