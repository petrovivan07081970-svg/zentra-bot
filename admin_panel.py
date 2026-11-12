"""Owner-only Telegram administration for the ZENTRA VPN demo bot."""

import html
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import database

OWNER_ID = 6089008298
SUBSCRIPTION_STATE_KEY = "admin_subscription_days"

ADMIN_HOME_TEXT = (
    "🔷 <b>ZENTRA ADMIN</b>\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "🛡 Закрытая панель владельца\n"
    "⚡ Статус: демонстрационный режим\n\n"
    "<i>Платежи и VPN-подключения отключены.</i>"
)


def configured_admin_ids() -> set[int]:
    """Parse the comma-, semicolon-, or whitespace-separated ADMIN_IDS secret."""
    raw = os.getenv("ADMIN_IDS", "")
    ids: set[int] = set()
    for group in raw.replace(";", ",").split(","):
        for item in group.split():
            if item.isdecimal():
                ids.add(int(item))
    return ids


def is_authorized_admin(user_id: int | None) -> bool:
    """Require both the configured allowlist and the fixed owner ID."""
    return user_id == OWNER_ID and OWNER_ID in configured_admin_ids()


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🟦 Пользователи", callback_data="admin:users"
                ),
                InlineKeyboardButton(
                    "📊 Статистика", callback_data="admin:stats"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🎟 Подписки", callback_data="admin:subscriptions"
                ),
                InlineKeyboardButton(
                    "⚙️ Настройки", callback_data="admin:settings"
                ),
            ],
            [InlineKeyboardButton("✖️ Закрыть", callback_data="admin:close")],
        ]
    )


def admin_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("↩️ В меню ZENTRA ADMIN", callback_data="admin:home")]]
    )


def subscriptions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎟 Выдать на 7 дней", callback_data="admin:grant:7"
                ),
                InlineKeyboardButton(
                    "🎟 Выдать на 30 дней", callback_data="admin:grant:30"
                ),
            ],
            [InlineKeyboardButton("↩️ Назад", callback_data="admin:home")],
        ]
    )


def cancel_grant_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Отмена", callback_data="admin:cancel_grant"
                )
            ]
        ]
    )


def _users_text() -> str:
    total = database.count_users()
    users = database.list_users(limit=10)
    lines = [
        "👥 <b>Пользователи</b>",
        f"Всего: <b>{total}</b>",
        "",
    ]
    if not users:
        lines.append("Пока нет зарегистрированных пользователей.")
    else:
        for row in users:
            name = html.escape(str(row["first_name"] or "Без имени"))
            username = row["username"]
            username_text = (
                f" · @{html.escape(str(username))}" if username else ""
            )
            lines.append(
                f"• <code>{row['telegram_id']}</code> — {name}{username_text}"
            )
        if total > len(users):
            lines.append(f"\nПоказаны последние {len(users)} пользователей.")
    return "\n".join(lines)


def _statistics_text() -> str:
    stats = database.get_statistics()
    return (
        "📊 <b>Статистика</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👥 Пользователей: <b>{stats['total_users']}</b>\n"
        f"🟢 Активны за 24 часа: <b>{stats['active_24h']}</b>\n"
        f"🔵 Активны за 7 дней: <b>{stats['active_7d']}</b>\n"
        f"⚡ Действий всего: <b>{stats['total_interactions']}</b>\n"
        f"🎟 Активных демо-подписок: <b>{stats['active_subscriptions']}</b>"
    )


def _subscriptions_text() -> str:
    stats = database.get_statistics()
    recent = database.list_recent_subscriptions(limit=5)
    lines = [
        "🎟 <b>Демо-подписки</b>",
        f"Активных: <b>{stats['active_subscriptions']}</b>",
        "",
    ]
    if recent:
        lines.append("<b>Последние выдачи:</b>")
        for row in recent:
            expires_at = html.escape(str(row["expires_at"]))
            lines.append(
                f"• <code>{row['telegram_id']}</code> — "
                f"{row['duration_days']} дн., до {expires_at} UTC"
            )
    else:
        lines.append("Выдач пока нет.")
    lines.append("\nВыдача только демонстрационная: без оплаты и VPN-доступа.")
    return "\n".join(lines)


def _settings_text() -> str:
    return (
        "⚙️ <b>Настройки ZENTRA ADMIN</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🔐 Доступ: владелец из ADMIN_IDS\n"
        "🧪 Режим: демонстрационный\n"
        "💳 Платежи: отключены\n"
        "🌐 VPN-конфигурации: не создаются\n"
        "🗃 Хранилище: SQLite\n"
        "🎟 Демо-сроки: 7 или 30 дней"
    )


async def admin_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None:
        return
    if user is None or not is_authorized_admin(user.id):
        await message.reply_text("⛔ Доступ к административной панели закрыт.")
        return

    context.user_data.pop(SUBSCRIPTION_STATE_KEY, None)
    database.record_user_activity(user)
    await message.reply_text(
        ADMIN_HOME_TEXT,
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML",
    )


async def admin_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None:
        return

    user = query.from_user
    if not is_authorized_admin(user.id):
        await query.answer("⛔ Доступ запрещён.", show_alert=True)
        return

    await query.answer()
    database.record_user_activity(user)
    callback_data = query.data or ""

    if callback_data == "admin:home":
        context.user_data.pop(SUBSCRIPTION_STATE_KEY, None)
        text = ADMIN_HOME_TEXT
        keyboard = admin_main_keyboard()
        parse_mode = "HTML"
    elif callback_data == "admin:users":
        text = _users_text()
        keyboard = admin_back_keyboard()
        parse_mode = "HTML"
    elif callback_data == "admin:stats":
        text = _statistics_text()
        keyboard = admin_back_keyboard()
        parse_mode = "HTML"
    elif callback_data == "admin:subscriptions":
        text = _subscriptions_text()
        keyboard = subscriptions_keyboard()
        parse_mode = "HTML"
    elif callback_data == "admin:settings":
        text = _settings_text()
        keyboard = admin_back_keyboard()
        parse_mode = "HTML"
    elif callback_data in {"admin:grant:7", "admin:grant:30"}:
        duration_days = int(callback_data.rsplit(":", maxsplit=1)[1])
        context.user_data[SUBSCRIPTION_STATE_KEY] = duration_days
        text = (
            "🎟 <b>Выдача демо-подписки</b>\n\n"
            f"Срок: <b>{duration_days} дней</b>\n"
            "Отправьте числовой Telegram ID зарегистрированного пользователя.\n"
            "Реального VPN-доступа эта операция не создаёт."
        )
        keyboard = cancel_grant_keyboard()
        parse_mode = "HTML"
    elif callback_data == "admin:cancel_grant":
        context.user_data.pop(SUBSCRIPTION_STATE_KEY, None)
        text = _subscriptions_text()
        keyboard = subscriptions_keyboard()
        parse_mode = "HTML"
    elif callback_data == "admin:close":
        context.user_data.pop(SUBSCRIPTION_STATE_KEY, None)
        await query.edit_message_text("Панель ZENTRA ADMIN закрыта.")
        return
    else:
        text = ADMIN_HOME_TEXT
        keyboard = admin_main_keyboard()
        parse_mode = "HTML"

    await query.edit_message_text(
        text,
        reply_markup=keyboard,
        parse_mode=parse_mode,
    )


async def handle_subscription_target(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    duration_days = context.user_data.get(SUBSCRIPTION_STATE_KEY)
    if duration_days not in (7, 30):
        return

    message = update.effective_message
    user = update.effective_user
    if message is None:
        return
    if user is None or not is_authorized_admin(user.id):
        context.user_data.pop(SUBSCRIPTION_STATE_KEY, None)
        await message.reply_text("⛔ Доступ запрещён.")
        return

    text = (message.text or "").strip()
    if not text.isascii() or not text.isdigit():
        await message.reply_text(
            "Отправьте числовой Telegram ID или нажмите «Отмена»."
        )
        return

    telegram_id = int(text)
    if telegram_id <= 0 or telegram_id > 9_223_372_036_854_775_807:
        await message.reply_text("Некорректный Telegram ID. Попробуйте ещё раз.")
        return

    grant = database.grant_demo_subscription(
        telegram_id=telegram_id,
        duration_days=duration_days,
        granted_by=user.id,
    )
    if grant is None:
        await message.reply_text(
            "Пользователь не найден в SQLite. Попросите его сначала отправить /start."
        )
        return

    context.user_data.pop(SUBSCRIPTION_STATE_KEY, None)
    expires_at = html.escape(str(grant["expires_at"]))
    await message.reply_text(
        f"✅ Демо-подписка на <b>{duration_days} дней</b> выдана "
        f"пользователю <code>{telegram_id}</code>.\n"
        f"Срок до: <code>{expires_at} UTC</code>.\n"
        "Оплата и VPN-подключение не выполнялись.",
        parse_mode="HTML",
        reply_markup=subscriptions_keyboard(),
    )


def register_admin_handlers(application: Application) -> None:
    """Register the protected admin command, callback route, and grant input."""
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(
        CallbackQueryHandler(admin_callback, pattern=r"^admin:")
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_subscription_target)
  )
          
