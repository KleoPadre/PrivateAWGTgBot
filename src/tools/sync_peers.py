#!/usr/bin/env python3
"""
Скрипт синхронизации peer'ов между базой бота и сервером AmneziaWG
Восстанавливает удаленные peer'ы при перезаписи конфигурации приложением
"""
import asyncio
import json
import subprocess
from pathlib import Path
import sys

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.database.repository import ConfigRepository
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


async def get_bot_configs():
    """Получить все активные конфигурации из базы бота"""
    configs = await ConfigRepository.get_all_configs()
    return configs


async def sync_peer(config):
    """Добавить peer на сервер"""
    try:
        # Проверяем, есть ли уже этот peer
        current_peers = await get_current_peers()
        if config['client_public_key'] in current_peers:
            logger.debug(f"Peer {config['config_name']} уже существует")
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


async def sync_all():
    """Синхронизировать всех peer'ов"""
    logger.info("🔄 Начинаем синхронизацию peer'ов...")
    
    # Получаем список peer'ов на сервере
    current_peers = await get_current_peers()
    logger.info(f"На сервере сейчас {len(current_peers)} peer(s)")
    
    # Получаем список конфигураций из базы
    bot_configs = await get_bot_configs()
    logger.info(f"В базе бота {len(bot_configs)} конфигураций")
    
    # Проверяем каждую конфигурацию
    restored = 0
    for config in bot_configs:
        if config['client_public_key'] not in current_peers:
            logger.warning(f"⚠️  Peer {config['config_name']} отсутствует на сервере, восстанавливаем...")
            if await sync_peer(config):
                restored += 1
                # Небольшая задержка между добавлениями
                await asyncio.sleep(0.5)
    
    if restored > 0:
        logger.info(f"✅ Восстановлено {restored} peer(s)")
    else:
        logger.info("✅ Все peer'ы на месте, восстановление не требуется")
    
    return restored


async def watch_mode():
    """Режим постоянного мониторинга"""
    logger.info("👁️  Запуск режима мониторинга...")
    logger.info("Проверка каждые 30 секунд")
    
    while True:
        try:
            await sync_all()
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
    
    parser = argparse.ArgumentParser(description='Синхронизация peer\'ов AmneziaWG')
    parser.add_argument(
        '--watch',
        action='store_true',
        help='Режим постоянного мониторинга'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Однократная синхронизация (по умолчанию)'
    )
    
    args = parser.parse_args()
    
    if args.watch:
        await watch_mode()
    else:
        await sync_all()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  Прервано пользователем")
        sys.exit(0)

