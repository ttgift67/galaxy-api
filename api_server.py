"""Сервер для кнопок «Обнулить всем» в мини-приложении.

Запуск:  pip install aiohttp  ->  python api_server.py
Переменные:
  BOT_TOKEN  — токен бота, из которого открывается мини-приложение (нужен для проверки админа)
  ADMIN_IDS  — Telegram ID админов через запятую, например 123456789,987654321
  PORT       — порт (по умолчанию 8080)
Нужен HTTPS (хостинг вроде Render/Railway или свой сервер с Caddy/nginx).
Адрес сервера впиши в API_URL в index.html.
"""
import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl

from aiohttp import web

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}
FILE = "epochs.json"


def load():
    try:
        with open(FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"bal": 0, "full": 0}


def save(d):
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(d, f)


def valid_user(init_data: str):
    """Проверка подписи Telegram: гарантирует, что запрос пришёл из твоего мини-приложения."""
    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True))
        got_hash = data.pop("hash")
        check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, got_hash):
            return None
        if time.time() - int(data.get("auth_date", "0")) > 86400:
            return None
        return json.loads(data["user"])
    except Exception:
        return None


@web.middleware
async def cors(request, handler):
    resp = web.Response() if request.method == "OPTIONS" else await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp


async def epoch(request):
    return web.json_response(load())


async def reset(request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "плохой запрос"}, status=400)
    user = valid_user(body.get("initData", ""))
    if not user or user.get("id") not in ADMIN_IDS:
        return web.json_response({"ok": False, "error": "нет доступа"}, status=403)
    mode = body.get("mode")
    if mode not in ("balance", "all"):
        return web.json_response({"ok": False, "error": "неизвестный режим"}, status=400)
    d = load()
    now = int(time.time() * 1000)  # время сброса: не откатывается, даже если файл потерялся при перезапуске
    d["bal"] = now           # любой сброс обнуляет баланс
    if mode == "all":
        d["full"] = now      # полный сброс обнуляет ещё и инвентарь
    save(d)
    return web.json_response({"ok": True, **d})


app = web.Application(middlewares=[cors])
app.add_routes([
    web.get("/api/epoch", epoch),
    web.post("/api/admin/reset", reset),
    web.options("/api/admin/reset", lambda r: web.Response()),
])

if __name__ == "__main__":
    web.run_app(app, port=int(os.getenv("PORT", "8080")))
