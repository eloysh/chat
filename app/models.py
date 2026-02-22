import os
from typing import Dict, List

APIFREE_BASE_URL = os.getenv("APIFREE_BASE_URL", "https://api.skycoding.ai").rstrip("/")

DEFAULT_CHAT_MODEL = os.getenv("DEFAULT_CHAT_MODEL", "openai/gpt-5.2")
GROK_CHAT_MODEL = os.getenv("GROK_CHAT_MODEL", "xai/grok-4")

DEFAULT_IMAGE_MODEL = os.getenv("DEFAULT_IMAGE_MODEL", "google/nano-banana-pro")
DEFAULT_VIDEO_MODEL = os.getenv("DEFAULT_VIDEO_MODEL", "klingai/kling-v2.6/pro/image-to-video")
DEFAULT_MUSIC_MODEL = os.getenv("DEFAULT_MUSIC_MODEL", "mureka-ai/mureka-v8/generate-song")

def get_models_catalog() -> Dict[str, List[Dict[str, str]]]:
    """
    Возвращает каталог моделей для UI /api/models
    """
    return {
        "chat": [
            {"id": DEFAULT_CHAT_MODEL, "title": "GPT (default)"},
            {"id": GROK_CHAT_MODEL, "title": "Grok"},
        ],
        "image": [
            {"id": DEFAULT_IMAGE_MODEL, "title": "Nano Banana Pro"},
        ],
        "video": [
            {"id": DEFAULT_VIDEO_MODEL, "title": "Kling Image→Video"},
        ],
        "music": [
            {"id": DEFAULT_MUSIC_MODEL, "title": "Mureka V8"},
        ],
    }
