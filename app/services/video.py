from app.apifree_client import apifree_post_with_optional_polling

async def run_video(model: str, payload: dict):
    data = await apifree_post_with_optional_polling(model, payload)
    return data
