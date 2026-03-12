from app.apifree_client import apifree_post_with_optional_polling

async def run_image(model: str, payload: dict):
    prompt = (payload.get("prompt") or "").strip()
    data = await apifree_post_with_optional_polling(model, {"prompt": prompt})
    return data
