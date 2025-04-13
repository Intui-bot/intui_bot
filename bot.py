
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

import openai
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

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
        reply = "Извини, возникла ошибка при обращении к ИИ. Попробуй позже."

    await update.message.reply_text(reply)

def main():
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()
