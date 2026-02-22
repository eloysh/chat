# Guurenko AI Mini App (Production)

## Render ENV (Environment Variables)
Set these in Render → Environment:

- BOT_TOKEN = your Telegram bot token
- PUBLIC_BASE_URL = https://guurenko-ai.onrender.com
- APIFREE_API_KEY = your API Free key
- APIFREE_BASE_URL = https://api.skycoding.ai  (or your API Free base)
- DB_PATH = /var/data/app.db

Optional:
- DEFAULT_CHAT_MODEL, GROK_CHAT_MODEL
- DEFAULT_IMAGE_MODEL, DEFAULT_VIDEO_MODEL, DEFAULT_MUSIC_MODEL
- APIFREE_HTTP_TIMEOUT_SEC

## Telegram webhook
After deploy, set webhook:
https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://guurenko-ai.onrender.com/telegram/webhook/hook

## Mini App URL
https://guurenko-ai.onrender.com/webapp/
