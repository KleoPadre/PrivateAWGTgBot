"""
Главный файл Telegram бота для выдачи конфигураций AmneziaWG
"""
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from src.config.settings import settings
from src.database.models import db
from src.bot.handlers.start import start_command
from src.bot.handlers.config import handle_phone_config, handle_laptop_config, handle_router_config
from src.bot.handlers.admin import (
    stats_command, users_command, reboot_command,
    handle_stats, handle_users, handle_reboot_server,
    handle_reboot_confirm, handle_reboot_cancel
)
from src.bot.filters import authorized_users_filter, admin_filter
from src.utils.logger import logger


async def post_init(application: Application) -> None:
    """
    Инициализация после запуска бота
    
    Args:
        application: Экземпляр приложения
    """
    # Инициализируем базу данных
    await db.init_db()
    logger.info("База данных инициализирована")
    
    # Валидируем настройки
    try:
        settings.validate()
        logger.info("Настройки валидны")
    except ValueError as e:
        logger.error(f"Ошибка валидации настроек: {e}")
        raise
    
    logger.info("Бот успешно запущен")


async def error_handler(update: object, context) -> None:
    """
    Обработчик ошибок
    
    Args:
        update: Объект обновления
        context: Контекст
    """
    logger.error(f"Произошла ошибка: {context.error}", exc_info=context.error)
    
    # Если есть update с сообщением, отправляем пользователю
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Произошла ошибка при обработке запроса.\n"
            "Пожалуйста, попробуйте позже или обратитесь к администратору."
        )


def main() -> None:
    """Запуск бота"""
    logger.info("Запуск AmneziaWG Bot...")
    
    # Создаем приложение
    application = (
        Application.builder()
        .token(settings.BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("users", users_command))
    application.add_handler(CommandHandler("reboot", reboot_command))
    
    # Регистрируем обработчики кнопок для обычных пользователей
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex("^📱 Для телефона$") & authorized_users_filter,
            handle_phone_config
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex("^💻 Для ноутбука$") & authorized_users_filter,
            handle_laptop_config
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex("^🌐 Для роутера$") & authorized_users_filter,
            handle_router_config
        )
    )
    
    # Регистрируем обработчики админ-кнопок
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex("^📊 Статистика$") & admin_filter,
            handle_stats
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex("^👥 Пользователи$") & admin_filter,
            handle_users
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex("^🔄 Перезагрузить сервер$") & admin_filter,
            handle_reboot_server
        )
    )
    
    # Регистрируем обработчики callback query (для inline кнопок)
    application.add_handler(CallbackQueryHandler(handle_reboot_confirm, pattern="^reboot_confirm$"))
    application.add_handler(CallbackQueryHandler(handle_reboot_cancel, pattern="^reboot_cancel$"))
    
    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Бот запущен и ожидает сообщений...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        raise

