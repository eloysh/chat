from app.apifree_client import apifree_post_with_optional_polling

async def run_music(model: str, payload: dict):
    lyrics = (payload.get("lyrics") or "").strip()
    style = (payload.get("style") or "").strip()
    req = {"lyrics": lyrics}
    if style:
        req["style"] = style
    return await apifree_post_with_optional_polling(model, req)
