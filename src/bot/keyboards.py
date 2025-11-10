"""
Клавиатуры для Telegram бота
"""
from telegram import ReplyKeyboardMarkup, KeyboardButton


def get_device_keyboard() -> ReplyKeyboardMarkup:
    """
    Клавиатура с выбором типа устройства
    
    Returns:
        ReplyKeyboardMarkup: Клавиатура
    """
    keyboard = [
        [KeyboardButton("📱 Для телефона"), KeyboardButton("💻 Для ноутбука"), KeyboardButton("🌐 Для роутера")]
    ]
    
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def get_admin_keyboard() -> ReplyKeyboardMarkup:
    """
    Клавиатура для администратора
    
    Returns:
        ReplyKeyboardMarkup: Клавиатура администратора
    """
    keyboard = [
        [KeyboardButton("📱 Для телефона"), KeyboardButton("💻 Для ноутбука"), KeyboardButton("🌐 Для роутера")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("👥 Пользователи"), KeyboardButton("🔄 Перезагрузить сервер")]
    ]
    
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )

