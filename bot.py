import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI

# Загрузка переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # добавь в Render

# Настройка логов
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# OpenAI клиент
client = OpenAI(api_key=OPENAI_API_KEY)

# Системный промпт
SYSTEM_PROMPT = (
    "Ты — Интуи, виртуальная интерпретаторка снов. "
    "Твой стиль — тёплый, философский, обволакивающий. "
    "Ты используешь образы, метафоры, мягкие советы. "
    "Анализируй каждый сон как отражение внутреннего мира человека."
)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        rf"Привет, {user.mention_html()}! ✨"
        "Я — Интуи, твой проводник по миру снов. Расскажи, что тебе приснилось."
    )

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_input = update.message.text
    await update.message.reply_text("Я думаю над твоим сном...")

    if not OPENAI_API_KEY:
        await update.message.reply_text("🔒 Интерпретация временно недоступна: ключ OpenAI не задан.")
        return

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input}
            ],
            max_tokens=700,
            temperature=0.8
        )
        reply = response.choices[0].message.content.strip()
    except Exception as e:
        reply = f"⚠️ Ошибка при обращении к ИИ: {e}"

    await update.message.reply_text(reply)

# Запуск бота с Webhook
async def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN не задан!")

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Настройка webhook
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(url=WEBHOOK_URL)
    await application.updater.start_polling()
    await application.updater.idle()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
