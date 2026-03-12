DEFAULT_CHAT_MODEL = "openai/gpt-5.2"
GROK_CHAT_MODEL = "xai/grok-4"
DEFAULT_IMAGE_MODEL = "google/nano-banana-pro"
DEFAULT_VIDEO_MODEL = "klingai/kling-v2.6/pro/image-to-video"
DEFAULT_MUSIC_MODEL = "mureka-ai/mureka-v8/generate-song"
def get_models_catalog():
    """
    Каталог моделей для Mini App
    """

    return {
        "chat": [
            {
                "id": "openai/gpt-5.2",
                "name": "GPT-5.2",
                "provider": "OpenAI"
            },
            {
                "id": "xai/grok-4",
                "name": "Grok-4",
                "provider": "xAI"
            }
        ],

        "image": [
            {
                "id": "google/nano-banana-pro",
                "name": "Nano Banana Pro",
                "provider": "Google"
            }
        ],

        "video": [
            {
                "id": "klingai/kling-v2.6/pro/image-to-video",
                "name": "Kling 2.6 Pro",
                "provider": "Kling"
            }
        ],

        "music": [
            {
                "id": "mureka-ai/mureka-v8/generate-song",
                "name": "Mureka V8",
                "provider": "Mureka"
            }
        ]
    }
