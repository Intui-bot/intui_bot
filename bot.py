
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import openai
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
else:
    print("⚠️ ВНИМАНИЕ: OPENAI_API_KEY не задан. Ответы от ИИ работать не будут.")

SYSTEM_PROMPT = (
    "Ты — Интуи, виртуальная интерпретаторка снов. "
    "Твой стиль — тёплый, философский, обволакивающий. "
    "Ты используешь образы, метафоры, мягкие советы. "
    "Анализируй каждый сон как отражение внутреннего мира человека."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        rf"Привет, {user.mention_html()}! ✨\n"
        "Я — Интуи, твой проводник по миру снов. Расскажи, что тебе приснилось."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_input = update.message.text
    await update.message.reply_text("Я думаю над твоим сном...")

    if not OPENAI_API_KEY:
        await update.message.reply_text("🔒 Интерпретация временно недоступна: ключ OpenAI не задан.")
        return

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input}
            ],
            max_tokens=700,
            temperature=0.8
        )
        reply = response.choices[0].message["content"].strip()
    except Exception as e:
        reply = f"⚠️ Ошибка при обращении к ИИ: {e}"

    await update.message.reply_text(reply)

def main():
    logging.basicConfig(level=logging.INFO)

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if not WEBHOOK_URL:
        print("❌ WEBHOOK_URL не задан. Завершаем работу.")
        return

    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        webhook_url=WEBHOOK_URL
    )


if __name__ == "__main__":
    main()
