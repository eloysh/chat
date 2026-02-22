import os
from typing import Any, Dict
from fastapi import HTTPException
from app.services.chat import apifree_post

DEFAULT_IMAGE_MODEL = os.getenv("DEFAULT_IMAGE_MODEL", "google/nano-banana-pro")

async def run_image(model: str, prompt: str) -> Dict[str, Any]:
    if not model:
        model = DEFAULT_IMAGE_MODEL
    create_payload = {"model": model, "prompt": prompt}
    data = await apifree_post("/v1/images/generations", create_payload)

    url = None
    if isinstance(data.get("data"), list) and data["data"]:
        url = data["data"][0].get("url")
    url = data.get("url") or url

    if not url:
        raise HTTPException(status_code=502, detail={"error": "no_url", "raw": data})

    return {"url": url, "raw": data}
