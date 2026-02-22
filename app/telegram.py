import os
import httpx
from typing import Optional

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TG_API = "https://api.telegram.org"

async def tg_send_message(chat_id: int, text: str):
    if not BOT_TOKEN:
        return
    async with httpx.AsyncClient(timeout=30) as client:
        await client.post(
            f"{TG_API}/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )

async def tg_send_photo(chat_id: int, url: str, caption: Optional[str] = None):
    if not BOT_TOKEN:
        return
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {"chat_id": chat_id, "photo": url}
        if caption:
            payload["caption"] = caption
        await client.post(f"{TG_API}/bot{BOT_TOKEN}/sendPhoto", json=payload)

async def tg_send_video(chat_id: int, url: str, caption: Optional[str] = None):
    if not BOT_TOKEN:
        return
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {"chat_id": chat_id, "video": url}
        if caption:
            payload["caption"] = caption
        await client.post(f"{TG_API}/bot{BOT_TOKEN}/sendVideo", json=payload)

async def tg_send_audio(chat_id: int, url: str, caption: Optional[str] = None):
    if not BOT_TOKEN:
        return
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {"chat_id": chat_id, "audio": url}
        if caption:
            payload["caption"] = caption
        await client.post(f"{TG_API}/bot{BOT_TOKEN}/sendAudio", json=payload)
