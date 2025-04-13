import os
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

SYSTEM_PROMPT = (
    "Ты — Интуи, виртуальная интерпретаторка снов. "
    "Твой стиль — тёплый, философский, обволакивающий. "
    "Ты используешь образы, метафоры, мягкие советы. "
    "Анализируй каждый сон как отражение внутреннего мира человека."
)

logging.basicConfig(level=logging.INFO)

# Обработка команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        rf"Привет, {user.mention_html()}! ✨"
        "Я — Интуи, твой проводник по миру снов. Расскажи, что тебе приснилось."
    )

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_input = update.message.text
    await update.message.reply_text("Я думаю над твоим сном...")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://t.me/Intui_Dream_Bot",  # или твой домен
        "X-Title": "Intui Dream Bot",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "openai/gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input}
        ],
        "temperature": 0.8,
        "max_tokens": 700
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=30)
        result = response.json()
        if "choices" in result:
            reply = result["choices"][0]["message"]["content"].strip()
        else:
            reply = f"⚠️ Ошибка OpenRouter: {result.get('error', {}).get('message', 'Неизвестная ошибка')}"
    except Exception as e:
        reply = f"⚠️ Ошибка при обращении к ИИ: {e}"

    await update.message.reply_text(reply)

# Запуск с webhook
if __name__ == "__main__":
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        webhook_url=WEBHOOK_URL
    )
