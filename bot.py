import os
import logging
import smtplib
import random
import time
from collections import deque
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

# Логируем ошибки и информацию о токенах
logging.basicConfig(
    filename="error.log",
    filemode="a",
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
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
        logging.error(f"Не удалось отправить email: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#                      Основные константы и переменные
# ─────────────────────────────────────────────────────────────────────────────

TELEGRAM_TOKEN     = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL        = os.getenv("WEBHOOK_URL")
ADMIN_TELEGRAM_ID  = 629449375   # Ваш Telegram ID для уведомлений об ошибках и usage

# Уменьшенные и оптимизированные промпты для экономии токенов
STYLE_PROMPTS = {
    "Мастер": (
        "Ты — виртуальный мастер толкования снов. "
        "Смотри на сон как на язык подсознания, ищи символы и связи с эмоциями. "
        "Твой стиль — уверенный и деликатный. "
        "В конце ОБЯЗАТЕЛЬНО добавляешь блок, начинающийся со слова: Совет: — "
        "и даёшь короткий, практичный, доброжелательный совет. "
        "Этот блок идёт в самом конце и начинается строго с 'Совет:'."
    ),
    "Психоаналитик": (
        "Ты — строгий интерпретатор снов, ученик Фрейда и Юнга. "
        "Анализируешь образы, эмоции и скрытые конфликты через психоанализ. "
        "В конце ОБЯЗАТЕЛЬНО добавляешь блок, начинающийся со слова: Совет: — "
        "и даёшь конкретный, лаконичный совет на основе анализа."
    ),
    "Мистик": (
        "Ты — загадочная прорицательница, говоришь образами и символами без «эзотерики». "
        "Интерпретируешь через архетипы и интуицию, но понятно и по делу. "
        "В конце ОБЯЗАТЕЛЬНО добавляешь блок, начинающийся со слова: Совет: — "
        "и даёшь мягкое, образное и практичное направление."
    )
}

DEFAULT_STYLE = "Мастер"       # Стиль по умолчанию
MAX_HISTORY_ENTRIES = 3       # Лимит записей истории

# ─────────────────────────────────────────────────────────────────────────────
#                           Команда /start
# ─────────────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Приветственное сообщение с кнопками:
     - 🌙 Рассказать сон
     - 🎭 Выбрать стиль
     - 📜 История снов
    Инициализирует user_data.
    """
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
        f"""Приветствую тебя, {user.mention_html()}! ✨
Я — Интуи, твоя проводница по миру снов.
У меня есть несколько вариантов стиля интерпретации сна.
Ты сможешь выбрать удобный стиль или сразу рассказать сон.
Что хочешь сделать?""",
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
     - style_<имя>      → устанавливает выбран стиль
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
            f"✅ Стиль интерпретации установлен: *{selected_style}*. Теперь опиши свой сон.",
            parse_mode="Markdown"
        )
        return


# ─────────────────────────────────────────────────────────────────────────────
#                       Команда /style (альтернативный вызов)
# ─────────────────────────────────────────────────────────────────────────────

async def style_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    При вызове /style выводит меню выбора стилей.
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
    сохраняет в историю (лимит 3), отвечает пользователю. Логирует ошибки и usage.
    """
    user_input = update.message.text
    await update.message.reply_text("🔮 Я думаю над твоим сном...")

    # Текущий стиль (по умолчанию "Мастер")
    style_name = context.user_data.get("style", DEFAULT_STYLE)
    prompt = STYLE_PROMPTS.get(style_name, STYLE_PROMPTS[DEFAULT_STYLE])

    try:
        # Инициализируем клиент OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        # Запрос к модели с оптимизированными параметрами
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_input}
            ],
            temperature=0.6,   # Снижение температуры для более сдержанных ответов
            max_tokens=500     # Ограничение длины ответа
        )

        # Логируем usage токенов
        usage = response.usage

        # Отправляем usage-статистику только администратору (не пользователю!)
        if update.effective_user.id == ADMIN_TELEGRAM_ID:
            await context.bot.send_message(
                chat_id=ADMIN_TELEGRAM_ID,
                text=(
                    f"📊 Новый запрос:\n"
                    f"Сон: {user_input[:30]}...\n"
                    f"Модель: gpt-4o\n"
                    f"Prompt tokens: {usage.prompt_tokens}\n"
                    f"Completion tokens: {usage.completion_tokens}\n"
                    f"Total tokens: {usage.total_tokens}"
                )
            )

        # Логируем usage в файл
        logging.info(
            f"Usage — Prompt: {usage.prompt_tokens} токенов, "
            f"Completion: {usage.completion_tokens} токенов, "
            f"Total: {usage.total_tokens} токенов."
        )

        # Собираем текст ответа
        reply_text = response.choices[0].message.content.strip()

        # Сохраняем в историю (только 3 записи)
        history = context.user_data.setdefault("history", [])
        history.append((user_input, reply_text, style_name))
        if len(history) > MAX_HISTORY_ENTRIES:
            history.pop(0)

    except Exception as e:
        # Внутренняя ошибка — логируем и уведомляем
        error_message = f"Ошибка при обращении к OpenAI: {e}"
        logging.error(error_message)
        send_error_email(subject="Intui Bot Error", body=error_message)

        # Уведомляем админа в Telegram
        try:
            await context.bot.send_message(
                chat_id=ADMIN_TELEGRAM_ID,
                text=f"⚠️ Интуи поймала ошибку:\n{error_message}"
            )
        except Exception as tg_err:
            logging.error(f"Ошибка при отправке Telegram-сообщения админу: {tg_err}")

        # Случайная поэтичная заглушка
        fallback_text = get_random_fallback()
        await update.message.reply_text(fallback_text)
        return  # Завершаем обработку, чтобы не шёл дальше

    # Форматирование ответа: выделяем блок "Совет:"
    if "Совет:" in reply_text:
        parts = reply_text.split("Совет:", maxsplit=1)
        main_text = parts[0].strip()
        advice_block = parts[1].strip()

        formatted_reply = (
            f"{main_text}\n\n"
            f"<b>📝 Совет:</b> <i>{advice_block}</i>"
        )
        await update.message.reply_html(formatted_reply)
    else:
        await update.message.reply_text(reply_text)


# ─────────────────────────────────────────────────────────────────────────────
#               Функции для случайных заглушек и мониторинга ошибок
# ─────────────────────────────────────────────────────────────────────────────

# Список поэтичных заглушек
fallback_replies = [
    "🌙 Сегодня Интуи немного задумалась... Попробуй рассказать этот сон чуть позже.",
    "✨ Иногда даже сны ускользают... Попробуй ещё раз — Интуи услышит.",
    "💤 Интуи на мгновение ушла вглубь себя. Возвращайся через пару минут.",
    "🔮 Сейчас Интуи на границе миров. Она скоро снова будет с тобой.",
    "🌌 Сегодня сны запутались в облаках. Завтра всё прояснится."
]

# Очередь временных меток ошибок за последние 10 минут
error_log = deque()

def get_random_fallback() -> str:
    """
    Возвращает случайную поэтичную заглушку из списка.
    """
    return random.choice(fallback_replies)

def handle_error(error_message: str) -> None:
    """
    Логирует ошибку, отправляет email и уведомление админу.
    При >=3 ошибках за 10 минут шлёт тревожное письмо.
    """
    now = time.time()
    error_log.append(now)

    while error_log and now - error_log[0] > 600:
        error_log.popleft()

    logging.error(error_message)
    send_error_email(subject="Intui Bot Error", body=error_message)

    if len(error_log) >= 3:
        alert_body = (
            f"Зафиксировано {len(error_log)} ошибок за последние 10 минут.\n"
            f"Последняя ошибка:\n{error_message}"
        )
        send_error_email(subject="⚠️ Множественные сбои Intui", body=alert_body)


# ─────────────────────────────────────────────────────────────────────────────
#                                  Запуск бота
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("style", style_cmd))
    application.add_handler(CommandHandler("history", history_cmd))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        webhook_url=WEBHOOK_URL
    )
