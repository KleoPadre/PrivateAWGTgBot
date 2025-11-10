#!/usr/bin/env python3
"""
Скрипт для очистки конфигураций и peer'ов
Использование: python3 src/tools/cleanup_configs.py [--all | --user USER_ID | --config CONFIG_ID]
"""
import asyncio
import sys
import argparse
import aiosqlite
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.database.repository import ConfigRepository, UserRepository
from src.database.models import db
from src.services.awg_manager import awg_manager
from src.config.settings import settings
from src.utils.logger import logger


async def remove_peer_from_server(public_key: str, config_name: str):
    """Удалить peer с сервера"""
    try:
        # Читаем конфигурацию
        read_cmd = f"docker exec {settings.AWG_CONTAINER} cat {settings.AWG_CONFIG_PATH}/wg0.conf"
        stdout, stderr, code = await awg_manager._execute_command(read_cmd)
        
        if code != 0:
            logger.error(f"Ошибка чтения конфигурации: {stderr}")
            return False
        
        # Удаляем секцию [Peer]
        lines = stdout.split('\n')
        new_lines = []
        skip = False
        
        for i, line in enumerate(lines):
            if line.strip().startswith('[Peer]'):
                # Проверяем, это ли нужный peer
                # Ищем PublicKey в следующих строках
                for j in range(i+1, min(i+5, len(lines))):
                    if f"PublicKey = {public_key}" in lines[j]:
                        skip = True
                        break
                if not skip:
                    new_lines.append(line)
            elif line.strip().startswith('['):
                skip = False
                new_lines.append(line)
            elif not skip:
                new_lines.append(line)
        
        # Записываем обновленную конфигурацию
        import tempfile
        import os
        
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.conf')
        temp_file.write('\n'.join(new_lines))
        temp_file.close()
        
        # Копируем в контейнер
        copy_cmd = f"docker cp {temp_file.name} {settings.AWG_CONTAINER}:{settings.AWG_CONFIG_PATH}/wg0.conf"
        stdout, stderr, code = await awg_manager._execute_command(copy_cmd)
        os.unlink(temp_file.name)
        
        if code != 0:
            logger.error(f"Ошибка записи конфигурации: {stderr}")
            return False
        
        # Применяем изменения
        await awg_manager._apply_config_changes()
        
        # Обновляем clientsTable
        await update_clients_table_remove(public_key)
        
        logger.info(f"✅ Peer {config_name} удален с сервера")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка удаления peer: {e}")
        return False


async def update_clients_table_remove(public_key: str):
    """Удалить клиента из clientsTable"""
    try:
        # Читаем таблицу
        read_cmd = f"docker exec {settings.AWG_CONTAINER} cat {settings.AWG_CONFIG_PATH}/clientsTable"
        stdout, stderr, code = await awg_manager._execute_command(read_cmd)
        
        if code != 0:
            return
        
        import json
        clients = json.loads(stdout) if stdout else []
        
        # Удаляем клиента
        clients = [c for c in clients if c.get('clientId') != public_key]
        
        # Записываем обратно
        import tempfile
        import os
        
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
        json.dump(clients, temp_file, indent=4, ensure_ascii=False)
        temp_file.close()
        
        copy_cmd = f"docker cp {temp_file.name} {settings.AWG_CONTAINER}:{settings.AWG_CONFIG_PATH}/clientsTable"
        await awg_manager._execute_command(copy_cmd)
        os.unlink(temp_file.name)
        
    except Exception as e:
        logger.error(f"Ошибка обновления clientsTable: {e}")


async def delete_config(config_id: int):
    """Удалить конфигурацию по ID"""
    # Получаем конфигурацию
    configs = await ConfigRepository.get_all_configs()
    config = next((c for c in configs if c['id'] == config_id), None)
    
    if not config:
        logger.error(f"Конфигурация {config_id} не найдена")
        return False
    
    logger.info(f"Удаление конфигурации: {config['config_name']} (ID: {config_id})")
    
    # Удаляем peer с сервера
    await remove_peer_from_server(config['client_public_key'], config['config_name'])
    
    # Удаляем из базы
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute("DELETE FROM configs WHERE id = ?", (config_id,))
        await conn.commit()
    
    logger.info(f"✅ Конфигурация {config['config_name']} удалена")
    return True


async def list_configs():
    """Показать все конфигурации"""
    configs = await ConfigRepository.get_all_configs()
    
    if not configs:
        print("📭 Конфигураций нет")
        return
    
    print(f"\n📋 Всего конфигураций: {len(configs)}\n")
    print(f"{'ID':<5} {'Пользователь':<20} {'Устройство':<10} {'IP':<15} {'Файл':<30}")
    print("-" * 90)
    
    for config in configs:
        # Получаем пользователя
        users = await UserRepository.get_all_users()
        user = next((u for u in users if u['id'] == config['user_id']), None)
        username = user['username'] if user and user['username'] else 'unknown'
        
        print(f"{config['id']:<5} {username:<20} {config['device_type']:<10} {config['client_ip']:<15} {config['config_name']:<30}")


async def delete_user_configs(user_id: int):
    """Удалить все конфигурации пользователя"""
    configs = await ConfigRepository.get_user_configs(user_id)
    
    if not configs:
        logger.info(f"У пользователя {user_id} нет конфигураций")
        return
    
    logger.info(f"Удаление {len(configs)} конфигураций пользователя {user_id}")
    
    for config in configs:
        await delete_config(config['id'])


async def delete_all_configs():
    """Удалить все конфигурации"""
    configs = await ConfigRepository.get_all_configs()
    
    if not configs:
        logger.info("Нет конфигураций для удаления")
        return
    
    print(f"\n⚠️  ВНИМАНИЕ! Будут удалены ВСЕ {len(configs)} конфигураций!")
    confirm = input("Введите 'YES' для подтверждения: ")
    
    if confirm != 'YES':
        print("Отменено")
        return
    
    logger.info(f"Удаление всех {len(configs)} конфигураций")
    
    for config in configs:
        await delete_config(config['id'])
    
    logger.info("✅ Все конфигурации удалены")


async def main():
    parser = argparse.ArgumentParser(description='Управление конфигурациями AmneziaWG')
    parser.add_argument('--list', action='store_true', help='Показать все конфигурации')
    parser.add_argument('--delete', type=int, metavar='CONFIG_ID', help='Удалить конфигурацию по ID')
    parser.add_argument('--delete-user', type=int, metavar='USER_ID', help='Удалить все конфигурации пользователя')
    parser.add_argument('--delete-all', action='store_true', help='Удалить ВСЕ конфигурации')
    
    args = parser.parse_args()
    
    if args.list:
        await list_configs()
    elif args.delete:
        await delete_config(args.delete)
    elif args.delete_user:
        await delete_user_configs(args.delete_user)
    elif args.delete_all:
        await delete_all_configs()
    else:
        parser.print_help()


if __name__ == "__main__":
    import aiosqlite
    from src.database.models import db
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  Прервано")
        sys.exit(0)

