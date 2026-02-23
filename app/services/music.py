from typing import Any, Dict
from app.services.apifree import apifree_post_with_optional_polling
from app.apifree_client import apifree_post_with_optional_polling
async def run_music(model: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    payload ожидает:
      - lyrics: str
      - style: str|None
    """
    lyrics = (payload.get("lyrics") or "").strip()
    style = (payload.get("style") or "").strip() or None

    # ВАЖНО: путь оставляем как в твоём UI-каталоге моделей
    # Но мы НЕ используем api.apifree.ai — используем APIFREE_BASE_URL из env.
    path = "model/mureka-ai/mureka-v8/generate-song"

    req = {"lyrics": lyrics}
    if style:
        req["style"] = style

    data = await apifree_post_with_optional_polling(
        path,
        req,
        request_timeout_s=120.0,
        max_wait_s=1800.0,   # музыка может быть долгой
        poll_every_s=3.0
    )
    return data
