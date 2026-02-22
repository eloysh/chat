from typing import Any, Dict
from fastapi import HTTPException
from app.services.chat import apifree_post

async def run_music(model: str, lyrics: str, style: str | None) -> Dict[str, Any]:
    # модель можно передавать в payload, если твоё API Free её требует
    payload: Dict[str, Any] = {"lyrics": lyrics}
    if model:
        payload["model"] = model
    if style:
        payload["style"] = style

    data = await apifree_post("/v1/music/generations", payload)

    url = data.get("url")
    if not url and isinstance(data.get("data"), list) and data["data"]:
        url = data["data"][0].get("url")

    if not url:
        raise HTTPException(status_code=502, detail={"error": "no_url", "raw": data})

    return {"url": url, "raw": data}
