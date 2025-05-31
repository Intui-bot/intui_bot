import os
import logging
import smtplib
from email.mime.text import MIMEText
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from openai import OpenAI

# ─────────────────────────────────────────────────────────────────────────────
#                    Настройка логирования и email-уведомлений
# ─────────────────────────────────────────────────────────────────────────────

# Логируем ошибки в файл error.log
logging.basicConfig(
    filename="error.log",
    filemode="a",
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.ERROR
)

# Функция для отправки письма с текстом ошибки (если настроен SMTP)
def send_error_email(subject: str, body: str) -> None:
    """
    Отправляет email с указанной темой и текстом (body).
    Требуются переменные окружения:
      EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT,
      EMAIL_USER, EMAIL_PASSWORD, EMAIL_TO
    """
    try:
        smtp_server = os.getenv("EMAIL_SMTP_SERVER")
        smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        email_user = os.getenv("EMAIL_USER")
        email_pass = os.getenv("EMAIL_PASSWORD")
        email_to = os.getenv("EMAIL_TO")

        if not all([smtp_server, smtp_port, email_user, email_pass, email_to]):
            # Если не все параметры заданы – просто выходим
            return

        msg = MIMEText(body, _charset="utf-8")
        msg["Subject"] = subject
        msg["From"] = email_user
        msg["To"] = email_to

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(email_user, email_pass)
            server.sendmail(email_user, [email_to], msg.as_string())
    except Exception as e:
        # Если отправка email неудачна – тоже логируем
        logging.error(f"Не удалось отправить email: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#                      Основные константы и переменные
# ─────────────────────────────────────────────────────────────────────────────

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL      = os.getenv("WEBHOOK_URL")

# Промпты для разных стилей интерпретации
STYLE_PROMPTS = {
    "София": (
        "Ты — Интуи, виртуальная интерпретаторка снов. "
        "Твой стиль — философская и мягкая, словно шелест листвы. "
        "Ты используешь поэтичные образы, метафоры, мягкие советы. "
        "Анализируй каждый сон как отражение внутреннего мира человека."
    ),
    "Мистик": (
        "Ты — Интуи, загадочная прорицательница. "
        "Говоришь образами, тайнами и символами, словно древняя жрица. "
        "Каждое слово – заклинание, каждая фраза – ключ к тайным посланиям. "
        "Раскрывай скрытые смыслы сна, опираясь на мистические знания."
    ),
    "Психоаналитик": (
        "Ты — Интуи, строгий интерпретатор снов, ученик Фрейда и Юнга. "
        "Твоя задача – анализировать архетипы, бессознательные желания, "
        "конфликты и символы. " 
        "Делай упор на психоаналитическую трактовку и глубокие инсайты."
    )
}

DEFAULT_STYLE = "София"  # Стиль по умолчанию
MAX_HISTORY_ENTRIES = 3  # Лимит записей истории

# ─────────────────────────────────────────────────────────────────────────────
#                           Команда /start
# ─────────────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Приветственное сообщение с кнопками:
     - 🌙 Рассказать сон
     - 🎭 Выбрать стиль
     - 📜 История снов
    Сбрасывает или инициализирует user_data.
    """
    # Инициализируем стиль и историю в user_data
    context.user_data["style"] = DEFAULT_STYLE
    context.user_data["history"] = []

    keyboard = [
        [InlineKeyboardButton("🌙 Рассказать сон", callback_data="write_dream")],
        [InlineKeyboardButton("🎭 Выбрать стиль", callback_data="choose_style")],
        [InlineKeyboardButton("📜 История снов", callback_data="show_history")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    user = update.effective_user
    await update.message.reply_html(
        rf"Привет, {user.mention_html()}! ✨\n"
        "Я — Интуи, твоя проводница по миру снов. "
        "Что хочешь сделать?",
        reply_markup=reply_markup
    )


# ─────────────────────────────────────────────────────────────────────────────
#                         Обработчик кнопок CallbackQuery
# ─────────────────────────────────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает нажатия Inline-кнопок:
     - write_dream      → просит пользователя написать сон
     - choose_style     → предлагает меню выбора стиля
     - show_history     → показывает последние 3 сна
     - style_<имя>      → устанавливает выбранный стиль
    """
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "write_dream":
        await query.edit_message_text("📝 Напиши мне, что тебе приснилось...")
        return

    if data == "choose_style":
        keyboard = [
            [InlineKeyboardButton(style_name, callback_data=f"style_{style_name}")]
            for style_name in STYLE_PROMPTS.keys()
        ]
        await query.edit_message_text(
            "🎭 Выбери стиль интерпретации:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "show_history":
        history = context.user_data.get("history", [])
        if not history:
            await query.edit_message_text("📜 История пока пуста.")
        else:
            text = "📜 Последние сны:\n\n"
            for i, (dream_text, _, style_name) in enumerate(reversed(history), 1):
                snippet = dream_text if len(dream_text) <= 40 else dream_text[:40] + "..."
                text += f"{i}. 💤 *{snippet}* — _{style_name}_\n"
            await query.edit_message_text(text, parse_mode="Markdown")
        return

    if data.startswith("style_"):
        selected_style = data.replace("style_", "")
        context.user_data["style"] = selected_style
        await query.edit_message_text(
            f"✅ Стиль интерпретации установлен: *{selected_style}*",
            parse_mode="Markdown"
        )
        return


# ─────────────────────────────────────────────────────────────────────────────
#                       Команда /style (альтернативный вызов)
# ─────────────────────────────────────────────────────────────────────────────

async def style_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    При вызове /style выводит то же меню стилей, что и кнопка.
    """
    keyboard = [
        [InlineKeyboardButton(style_name, callback_data=f"style_{style_name}")]
        for style_name in STYLE_PROMPTS.keys()
    ]
    await update.message.reply_text(
        "🎭 Выбери стиль интерпретации:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ─────────────────────────────────────────────────────────────────────────────
#                    Команда /history (альтернативный вызов)
# ─────────────────────────────────────────────────────────────────────────────

async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    При вызове /history выводит до 3 последних снов.
    """
    history = context.user_data.get("history", [])
    if not history:
        await update.message.reply_text("📜 История пока пуста.")
    else:
        text = "📜 Последние сны:\n\n"
        for i, (dream_text, _, style_name) in enumerate(reversed(history), 1):
            snippet = dream_text if len(dream_text) <= 40 else dream_text[:40] + "..."
            text += f"{i}. 💤 *{snippet}* — _{style_name}_\n"
        await update.message.reply_text(text, parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────────────────
#                      Обработка текстовых сообщений (сны)
# ─────────────────────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Основная логика: принимает текст (сон), запрашивает интерпретацию у OpenAI,
    сохраняет в историю (лимит 3), отвечает пользователю. Логирует ошибки.
    """
    user_input = update.message.text
    await update.message.reply_text("🔮 Я думаю над твоим сном...")

    # Получаем текущий стиль (если не задан — DEFAULT_STYLE)
    style_name = context.user_data.get("style", DEFAULT_STYLE)
    prompt = STYLE_PROMPTS.get(style_name, STYLE_PROMPTS[DEFAULT_STYLE])

    try:
        # Инициализируем клиент OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        # Запрос к модели
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_input}
            ],
            temperature=0.8,
            max_tokens=700
        )
        reply_text = response.choices[0].message.content.strip()

        # Сохраняем в историю (только 3 записи)
        history = context.user_data.setdefault("history", [])
        history.append((user_input, reply_text, style_name))
        if len(history) > MAX_HISTORY_ENTRIES:
            history.pop(0)

    except Exception as e:
        # Формируем сообщение об ошибке и логируем
        error_message = f"Ошибка при обращении к OpenAI: {e}"
        logging.error(error_message)

        # Попытка отправить email (если настроен SMTP)
        send_error_email(
            subject="Intui Bot Error",
            body=error_message
        )

        reply_text = f"⚠️ {error_message}"

    await update.message.reply_text(reply_text)


# ─────────────────────────────────────────────────────────────────────────────
#                                  Запуск бота
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("style", style_cmd))
    application.add_handler(CommandHandler("history", history_cmd))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск Webhook
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        webhook_url=WEBHOOK_URL
    )
