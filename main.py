"""Demo-only Russian-language Telegram bot for ZENTRA VPN."""

import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import InvalidToken
from telegram.request import HTTPXRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

import database
from admin_panel import register_admin_handlers

LOGGER = logging.getLogger(__name__)

BRAND_HEADER = (
    "🔵 ZENTRA VPN\n"
    "Твой VPN. Твои правила.\n"
    "━━━━━━━━━━━━━━━━━━"
)

WELCOME_TEXT = (
    f"{BRAND_HEADER}\n\n"
    "Добро пожаловать!\nВыберите раздел ниже.\n\n"
    "🧪 Демонстрационный режим: платежи и VPN-подключение отключены."
)

SECTION_TEXT = {
    "tariffs": (
        "💳 Тарифы ZENTRA VPN\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🔹 START — 99 ₽ / месяц\n"
        "Базовый демонстрационный вариант.\n\n"
        "🔷 PRO — 199 ₽ / месяц\n"
        "Расширенный демонстрационный вариант.\n\n"
        "💠 ULTRA — 299 ₽ / месяц\n"
        "Максимальный демонстрационный вариант.\n\n"
        "🧪 Стоимость указана только для примера. Оплатить тарифы нельзя; "
        "платёжные системы не подключены."
    ),
    "support": (
        "🆘 Поддержка\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Чтобы подготовить сообщение об ошибке:\n"
        "1. Запишите, что вы нажали перед сбоем.\n"
        "2. Скопируйте точный текст ошибки.\n"
        "3. Укажите модель устройства и версию Telegram, если знаете их.\n"
        "4. Перед отправкой скройте личные данные на скриншотах.\n\n"
        "Не отправляйте токены и пароли. Контакт поддержки в демо не настроен, "
        "бот не принимает обращения."
    ),
    "about": (
        "ℹ️ О проекте\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "ZENTRA VPN — демонстрационный интерфейс VPN-сервиса.\n\n"
        "Твой VPN. Твои правила.\n\n"
        "Проект находится в разработке. Эта версия — демонстрация интерфейса: "
        "она не подключает VPN и не принимает оплату."
    ),
}

COUNTRY_LABELS = {
    "de": "🇩🇪 Германия",
    "nl": "🇳🇱 Нидерланды",
    "pl": "🇵🇱 Польша",
}

DEVICE_LABELS = {
    "android": "🤖 Android",
    "iphone": "🍎 iPhone",
}


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Build the main inline menu."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔵 Подключить VPN", callback_data="vpn:screen")],
            [
                InlineKeyboardButton("🌍 Выбрать страну", callback_data="country:menu"),
                InlineKeyboardButton("📱 Моё устройство", callback_data="device:menu"),
            ],
            [
                InlineKeyboardButton(
                    "📦 Моя подписка", callback_data="section:subscription"
                ),
                InlineKeyboardButton("💳 Тарифы", callback_data="section:tariffs"),
            ],
            [
                InlineKeyboardButton("👤 Мой аккаунт", callback_data="section:account"),
                InlineKeyboardButton("🆘 Поддержка", callback_data="section:support"),
            ],
            [InlineKeyboardButton("ℹ️ О проекте", callback_data="section:about")],
        ]
    )


def back_to_menu_keyboard(label: str = "↩️ Назад") -> InlineKeyboardMarkup:
    """Build a single-button keyboard for returning to the main menu."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data="menu:home")]]
    )


def vpn_screen_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔵 Подключить", callback_data="vpn:connect"),
                InlineKeyboardButton("⚪ Отключить", callback_data="vpn:disconnect"),
            ],
            [InlineKeyboardButton("↩️ Назад", callback_data="menu:home")],
        ]
    )


def country_selection_keyboard(
    selected_country: str | None = None,
) -> InlineKeyboardMarkup:
    rows = []
    for country, label in COUNTRY_LABELS.items():
        button_label = f"✅ {label}" if country == selected_country else label
        rows.append(
            [
                InlineKeyboardButton(
                    button_label,
                    callback_data=f"country:select:{country}",
                )
            ]
        )
    rows.append([InlineKeyboardButton("↩️ Назад", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def device_selection_keyboard(
    selected_device: str | None = None,
) -> InlineKeyboardMarkup:
    rows = []
    for device, label in DEVICE_LABELS.items():
        button_label = f"✅ {label}" if device == selected_device else label
        rows.append(
            [
                InlineKeyboardButton(
                    button_label,
                    callback_data=f"device:select:{device}",
                )
            ]
        )
    rows.append([InlineKeyboardButton("↩️ Назад", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def _selected_label(
    user_id: int, preference: str, labels: dict[str, str]
) -> str:
    preferences = database.get_user_preferences(user_id)
    selected = preferences.get(preference) if preferences else None
    return labels.get(selected or "", "Не выбрано")


def connection_screen_text(user_id: int, notice: str | None = None) -> str:
    text = (
        f"{BRAND_HEADER}\n"
        "Статус: 🔴 Не подключён\n"
        f"🌍 Страна: {_selected_label(user_id, 'selected_country', COUNTRY_LABELS)}\n"
        f"📱 Устройство: {_selected_label(user_id, 'selected_device', DEVICE_LABELS)}\n\n"
        "🧪 Реального VPN-подключения в демо нет."
    )
    return f"{text}\n\n{notice}" if notice else text


def country_screen_text(user_id: int) -> str:
    return (
        "🌍 Выберите страну\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"Сейчас выбрана: {_selected_label(user_id, 'selected_country', COUNTRY_LABELS)}"
    )


def device_screen_text(user_id: int) -> str:
    return (
        "📱 Моё устройство\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"Сейчас выбрано: {_selected_label(user_id, 'selected_device', DEVICE_LABELS)}"
    )


def subscription_text(user_id: int | None) -> str:
    if user_id is None:
        return "📦 Моя подписка\n\nДанные пользователя недоступны."

    tariff, status, expires_at = _subscription_details(user_id)

    return (
        "📦 Моя подписка\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"Тариф: {tariff}\n"
        f"Статус: {status}\n"
        f"Окончание: {expires_at}\n\n"
        "🧪 Это демонстрационная информация. Оплата и VPN-доступ отключены."
    )


def _subscription_details(user_id: int) -> tuple[str, str, str]:
    subscription = database.get_user_subscription(user_id)
    if subscription is None:
        return "Не выдан", "Не активна", "—"

    tariff = f"Демо на {subscription['duration_days']} дней"
    status = "Активна (демо)" if subscription["is_active"] else "Истекла (демо)"
    expires_at = f"{subscription['expires_at']} UTC"
    return tariff, status, expires_at


def account_text(update: Update) -> str:
    """Return a demo account summary for the current Telegram user."""
    user = update.effective_user
    if user is None:
        return "Мой аккаунт\n\nДанные пользователя недоступны."

    preferences = database.get_user_preferences(user.id) or {}
    tariff, subscription_status, expires_at = _subscription_details(user.id)

    return (
        "👤 Мой аккаунт\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"Telegram ID: {user.id}\n"
        f"Страна: {COUNTRY_LABELS.get(preferences.get('selected_country'), 'Не выбрана')}\n"
        f"Устройство: {DEVICE_LABELS.get(preferences.get('selected_device'), 'Не выбрано')}\n"
        f"Текущий тариф: {tariff}\n"
        f"Статус подписки: {subscription_status}\n"
        f"Окончание: {expires_at}"
    )


async def show_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show the main menu for /start, /menu, and /help."""
    del context
    database.record_user_activity(update.effective_user)
    message = update.effective_message
    if message is not None:
        await message.reply_text(WELCOME_TEXT, reply_markup=main_menu_keyboard())


async def show_my_id(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Reply with the numeric Telegram ID of the user who sent /myid."""
    del context
    message = update.effective_message
    user = update.effective_user

    if message is None:
        return
    if user is None:
        await message.reply_text("Не удалось определить ваш Telegram ID.")
        return

    database.record_user_activity(user)
    await message.reply_text(f"Ваш Telegram ID: {user.id}")


async def handle_menu_button(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Render the selected section by editing the current bot message."""
    del context
    query = update.callback_query
    if query is None:
        return

    user = query.from_user
    if user is None:
        await query.answer("Не удалось определить пользователя.", show_alert=True)
        return

    database.record_user_activity(user)
    await query.answer()
    callback_data = query.data or ""

    if callback_data == "menu:home":
        text = WELCOME_TEXT
        keyboard = main_menu_keyboard()
    elif callback_data in {"vpn:screen", "vpn:connect", "vpn:disconnect"}:
        notice = None
        if callback_data == "vpn:connect":
            notice = "🧪 Демо-режим: VPN пока не подключён."
        elif callback_data == "vpn:disconnect":
            notice = "ℹ️ VPN уже не подключён (демо-режим)."
        text = connection_screen_text(user.id, notice=notice)
        keyboard = vpn_screen_keyboard()
    elif callback_data == "country:menu":
        preferences = database.get_user_preferences(user.id) or {}
        selected_country = preferences.get("selected_country")
        text = country_screen_text(user.id)
        keyboard = country_selection_keyboard(selected_country)
    elif callback_data.startswith("country:select:"):
        country = callback_data.removeprefix("country:select:")
        if country in COUNTRY_LABELS and database.set_user_country(user.id, country):
            text = f"✅ Страна сохранена: {COUNTRY_LABELS[country]}\n\n{country_screen_text(user.id)}"
            keyboard = country_selection_keyboard(country)
        else:
            text = "Не удалось сохранить выбор. Откройте /start и попробуйте ещё раз."
            keyboard = back_to_menu_keyboard()
    elif callback_data == "device:menu":
        preferences = database.get_user_preferences(user.id) or {}
        selected_device = preferences.get("selected_device")
        text = device_screen_text(user.id)
        keyboard = device_selection_keyboard(selected_device)
    elif callback_data.startswith("device:select:"):
        device = callback_data.removeprefix("device:select:")
        if device in DEVICE_LABELS and database.set_user_device(user.id, device):
            text = f"✅ Устройство сохранено: {DEVICE_LABELS[device]}\n\n{device_screen_text(user.id)}"
            keyboard = device_selection_keyboard(device)
        else:
            text = "Не удалось сохранить выбор. Откройте /start и попробуйте ещё раз."
            keyboard = back_to_menu_keyboard()
    elif callback_data.startswith("section:"):
        section = callback_data.removeprefix("section:")
        if section == "account":
            text = account_text(update)
        elif section == "subscription":
            text = subscription_text(user.id)
        else:
            text = SECTION_TEXT.get(section, "Раздел не найден.")
        keyboard = back_to_menu_keyboard("↩️ В меню")
    else:
        text = "Не удалось открыть раздел. Вернитесь в главное меню."
        keyboard = back_to_menu_keyboard()

    await query.edit_message_text(text, reply_markup=keyboard)


def main() -> None:
    """Start the bot using the BOT_TOKEN environment secret."""
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit(
            "Не найден BOT_TOKEN. Добавьте токен Telegram-бота в Replit Secrets."
        )

    database.initialize_database()

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    # HTTPX logs full Telegram API URLs at INFO, which include the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    request = HTTPXRequest(
        connect_timeout=10,
        read_timeout=20,
        write_timeout=20,
        pool_timeout=10,
    )
    application = Application.builder().token(token).request(request).build()
    application.add_handler(
        CommandHandler(["start", "menu", "help"], show_menu)
    )
    application.add_handler(CommandHandler("myid", show_my_id))
    register_admin_handlers(application)
    application.add_handler(CallbackQueryHandler(handle_menu_button))

    LOGGER.info("ZENTRA VPN demo bot is starting.")
    try:
        application.run_polling(
            bootstrap_retries=3,
            drop_pending_updates=False,
        )
    except InvalidToken:
        raise SystemExit(
            "Telegram rejected BOT_TOKEN. Replace it in Replit Secrets."
        ) from None


if __name__ == "__main__":
    main()
      
