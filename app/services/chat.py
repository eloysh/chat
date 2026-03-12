from app.apifree_client import chat_completion


async def run_chat(model: str, prompt: str):
    data = await chat_completion(model, prompt)

    text = None

    try:
        text = data["choices"][0]["message"]["content"]
    except Exception:
        text = str(data)

    return {
        "text": text,
        "raw": data
    }
