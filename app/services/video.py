from typing import Any, Dict
from app.services.apifree import apifree_post_with_optional_polling

async def run_video(model: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    prompt = (payload.get("prompt") or payload.get("text") or "").strip()

    # пример: поменяй на реальные пути твоих video-моделей
    path = "model/skywork-ai/skyreels-v3/pro/single-avatar"

    req = {"prompt": prompt}
    data = await apifree_post_with_optional_polling(
        path,
        req,
        request_timeout_s=120.0,
        max_wait_s=2400.0,   # видео часто дольше
        poll_every_s=3.0
    )
    return data
