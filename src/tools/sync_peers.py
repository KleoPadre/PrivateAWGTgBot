#!/usr/bin/env python3
"""
Умная синхронизация peer'ов между базой бота и сервером AmneziaWG
- Восстанавливает peer'ы при случайном удалении (сбой, перезапись)
- Удаляет из базы при намеренном удалении через приложение AmneziaVPN
"""
import asyncio
import json
import subprocess
import aiosqlite
from pathlib import Path
import sys

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.database.repository import ConfigRepository
from src.database.models import db
from src.services.awg_manager import awg_manager
from src.config.settings import settings
from src.utils.logger import logger


async def get_current_peers():
    """Получить список текущих peer'ов на сервере"""
    cmd = f"docker exec {settings.AWG_CONTAINER} wg show wg0 peers"
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await process.communicate()
    peers = stdout.decode().strip().split('\n')
    return [p for p in peers if p]


async def get_clients_table():
    """Получить clientsTable (список клиентов в приложении)"""
    try:
        read_cmd = f"docker exec {settings.AWG_CONTAINER} cat {settings.AWG_CONFIG_PATH}/clientsTable"
        stdout, stderr, code = await awg_manager._execute_command(read_cmd)
        
        if code != 0:
            logger.warning("ClientsTable не найдена или пуста")
            return {}
        
        clients = json.loads(stdout) if stdout else []
        # Возвращаем словарь: {publicKey: clientData}
        return {c.get('clientId'): c for c in clients}
        
    except Exception as e:
        logger.error(f"Ошибка чтения clientsTable: {e}")
        return {}


async def get_bot_configs():
    """Получить все активные конфигурации из базы бота"""
    configs = await ConfigRepository.get_all_configs()
    return configs


async def delete_config_from_db(config_id: int, config_name: str):
    """Удалить конфигурацию из базы бота"""
    try:
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute("DELETE FROM configs WHERE id = ?", (config_id,))
            await conn.commit()
        logger.info(f"🗑️  Удален из базы бота: {config_name}")
        return True
    except Exception as e:
        logger.error(f"Ошибка удаления конфига из базы: {e}")
        return False


async def cleanup_empty_users():
    """Удалить пользователей без конфигураций"""
    try:
        from src.database.repository import UserRepository
        
        # Получаем всех пользователей
        users = await UserRepository.get_all_users()
        
        deleted = 0
        for user in users:
            # Проверяем, есть ли у пользователя конфигурации
            async with aiosqlite.connect(db.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM configs WHERE user_id = ?",
                    (user['id'],)
                )
                count = await cursor.fetchone()
                
                if count[0] == 0:
                    # У пользователя нет конфигов, удаляем
                    username = user.get('username') or user.get('first_name') or f"ID:{user['telegram_id']}"
                    
                    # Удаляем историю запросов
                    await conn.execute("DELETE FROM requests WHERE user_id = ?", (user['id'],))
                    # Удаляем пользователя
                    await conn.execute("DELETE FROM users WHERE id = ?", (user['id'],))
                    await conn.commit()
                    
                    logger.info(f"🗑️  Удален пустой пользователь: {username}")
                    deleted += 1
        
        if deleted > 0:
            logger.info(f"✅ Очищено {deleted} пользователей без конфигов")
        
        return deleted
        
    except Exception as e:
        logger.error(f"Ошибка очистки пустых пользователей: {e}")
        return 0


async def restore_peer(config):
    """Восстановить peer на сервере"""
    try:
        # Проверяем, есть ли уже этот peer
        current_peers = await get_current_peers()
        if config['client_public_key'] in current_peers:
            return False
        
        # Убираем .conf из имени для красивого отображения
        display_name = config['config_name'].replace('.conf', '')
        
        # Добавляем peer
        await awg_manager.add_peer_to_server(
            client_public_key=config['client_public_key'],
            client_ip=config['client_ip'],
            client_name=display_name
        )
        
        logger.info(f"✅ Восстановлен peer: {display_name} ({config['client_ip']})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка восстановления peer {config['config_name']}: {e}")
        return False


async def smart_sync():
    """
    Умная синхронизация:
    - Если peer'а нет НА СЕРВЕРЕ и НЕТ В CLIENTSTABLE → удалить из базы бота (намеренное удаление)
    - Если peer'а нет НА СЕРВЕРЕ, но ЕСТЬ В CLIENTSTABLE → восстановить (случайный сбой)
    """
    logger.info("🔄 Начинаем умную синхронизацию peer'ов...")
    
    # Получаем данные из всех источников
    current_peers = await get_current_peers()
    clients_table = await get_clients_table()
    bot_configs = await get_bot_configs()
    
    logger.info(f"На сервере: {len(current_peers)} peer(s)")
    logger.info(f"В clientsTable: {len(clients_table)} записей")
    logger.info(f"В базе бота: {len(bot_configs)} конфигураций")
    
    restored = 0
    deleted = 0
    
    for config in bot_configs:
        public_key = config['client_public_key']
        config_name = config['config_name']
        
        on_server = public_key in current_peers
        in_clients_table = public_key in clients_table
        
        if not on_server:
            if not in_clients_table:
                # Peer'а нет НИ на сервере, НИ в clientsTable
                # = НАМЕРЕННОЕ УДАЛЕНИЕ через приложение
                logger.warning(f"🗑️  {config_name}: удален через приложение, удаляем из базы бота")
                if await delete_config_from_db(config['id'], config_name):
                    deleted += 1
                    
            else:
                # Peer'а нет на сервере, НО ЕСТЬ в clientsTable
                # = СЛУЧАЙНОЕ УДАЛЕНИЕ (сбой, перезапись)
                logger.warning(f"🔄 {config_name}: случайное удаление, восстанавливаем...")
                if await restore_peer(config):
                    restored += 1
                await asyncio.sleep(0.5)
    
    # Очистка пользователей без конфигов
    empty_users = await cleanup_empty_users()
    
    # Итоги
    if restored > 0 or deleted > 0 or empty_users > 0:
        logger.info(f"📊 Итого: восстановлено {restored}, удалено конфигов {deleted}, удалено пустых пользователей {empty_users}")
    else:
        logger.info("✅ Все peer'ы синхронизированы, действий не требуется")
    
    return restored, deleted, empty_users


async def watch_mode():
    """Режим постоянного мониторинга"""
    logger.info("👁️  Запуск режима умного мониторинга...")
    logger.info("Проверка каждые 30 секунд")
    logger.info("🧠 Логика:")
    logger.info("   • Нет на сервере + нет в clientsTable = намеренное удаление → удалить из базы")
    logger.info("   • Нет на сервере + есть в clientsTable = случайный сбой → восстановить")
    
    while True:
        try:
            await smart_sync()
            await asyncio.sleep(30)  # Проверка каждые 30 секунд
        except KeyboardInterrupt:
            logger.info("\n⏹️  Остановка мониторинга")
            break
        except Exception as e:
            logger.error(f"Ошибка в цикле мониторинга: {e}")
            await asyncio.sleep(30)


async def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Умная синхронизация peer\'ов AmneziaWG')
    parser.add_argument(
        '--watch',
        action='store_true',
        help='Режим постоянного мониторинга (рекомендуется)'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Однократная синхронизация'
    )
    
    args = parser.parse_args()
    
    if args.watch:
        await watch_mode()
    else:
        await smart_sync()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  Прервано пользователем")
        sys.exit(0)
