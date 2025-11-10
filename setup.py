#!/usr/bin/env python3
"""
Скрипт автоматической настройки AmneziaWG Config Bot
Извлекает параметры из Docker контейнера и настраивает .env файл
"""
import subprocess
import os
import sys
import re
from pathlib import Path


def run_command(command):
    """Выполнение команды и возврат результата"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout.strip(), result.returncode
    except Exception as e:
        print(f"❌ Ошибка выполнения команды: {e}")
        return "", 1


def check_docker():
    """Проверка наличия Docker"""
    print("🔍 Проверка Docker...")
    output, code = run_command("docker --version")
    if code != 0:
        print("❌ Docker не установлен или недоступен")
        return False
    print(f"✅ {output}")
    return True


def check_amnezia_container():
    """Проверка наличия контейнера AmneziaWG"""
    print("\n🔍 Проверка контейнера AmneziaWG...")
    output, code = run_command("docker ps --filter name=amnezia-awg --format '{{.Names}}'")
    if code != 0 or not output:
        print("❌ Контейнер amnezia-awg не найден или не запущен")
        print("   Убедитесь, что AmneziaWG установлен и работает")
        return False
    print(f"✅ Контейнер найден: {output}")
    return True


def get_server_config():
    """Получение конфигурации сервера из контейнера"""
    print("\n📋 Чтение конфигурации сервера...")
    
    # Читаем конфигурацию
    config_cmd = "docker exec amnezia-awg cat /opt/amnezia/awg/wg0.conf"
    config_output, code = run_command(config_cmd)
    
    if code != 0:
        print("❌ Не удалось прочитать конфигурацию")
        return None
    
    config = {}
    
    # Извлекаем параметры из конфигурации
    # Публичный ключ сервера
    public_key_match = re.search(r'PublicKey\s*=\s*(\S+)', config_output)
    if public_key_match:
        # Нужно получить публичный ключ сервера из приватного
        private_key_match = re.search(r'PrivateKey\s*=\s*(\S+)', config_output)
        if private_key_match:
            private_key = private_key_match.group(1)
            pubkey_cmd = f"echo '{private_key}' | docker exec -i amnezia-awg wg pubkey"
            public_key, _ = run_command(pubkey_cmd)
            config['SERVER_PUBLIC_KEY'] = public_key
    
    # PresharedKey из секции [Peer]
    psk_match = re.search(r'PresharedKey\s*=\s*(\S+)', config_output)
    if psk_match:
        config['PRESHARED_KEY'] = psk_match.group(1)
    
    # ListenPort
    port_match = re.search(r'ListenPort\s*=\s*(\d+)', config_output)
    if port_match:
        config['PORT'] = port_match.group(1)
    
    # AmneziaWG параметры
    for param in ['Jc', 'Jmin', 'Jmax', 'S1', 'S2', 'H1', 'H2', 'H3', 'H4']:
        match = re.search(f'{param}\\s*=\\s*(\\d+)', config_output)
        if match:
            config[param.upper()] = match.group(1)
    
    # Сеть клиентов
    address_match = re.search(r'Address\s*=\s*([0-9.]+/\d+)', config_output)
    if address_match:
        network = address_match.group(1)
        config['CLIENT_NETWORK'] = network
        # Определяем стартовый IP для клиентов
        base_ip = network.split('/')[0]
        octets = base_ip.split('.')
        # Берем следующий IP после сервера (обычно .1)
        next_ip = '.'.join(octets[:-1] + [str(max(2, int(octets[-1]) + 1))])
        
        # Проверяем, какие IP уже заняты
        allowed_ips = re.findall(r'AllowedIPs\s*=\s*([0-9.]+)/32', config_output)
        if allowed_ips:
            used_octets = [int(ip.split('.')[-1]) for ip in allowed_ips]
            max_used = max(used_octets) if used_octets else 1
            next_ip = '.'.join(octets[:-1] + [str(max_used + 1)])
        
        config['CLIENT_IP_START'] = next_ip
    
    return config


def get_server_ip():
    """Получение внешнего IP адреса сервера"""
    print("\n🌐 Определение внешнего IP адреса...")
    
    # Пробуем разные сервисы
    services = [
        "curl -s ifconfig.me",
        "curl -s icanhazip.com",
        "curl -s ipinfo.io/ip"
    ]
    
    for service in services:
        ip, code = run_command(service)
        if code == 0 and ip and re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
            print(f"✅ Внешний IP: {ip}")
            return ip
    
    print("⚠️  Не удалось определить внешний IP автоматически")
    return None


def create_env_file(bot_token, admin_id, users, server_config, server_ip):
    """Создание .env файла с конфигурацией"""
    print("\n📝 Создание .env файла...")
    
    env_content = f"""# Telegram Bot Configuration
BOT_TOKEN={bot_token}

# Admin Configuration
ADMIN_ID={admin_id}

# Allowed Users (comma-separated Telegram IDs)
USERS={users}

# AmneziaWG Configuration
AWG_CONTAINER=amnezia-awg
AWG_CONFIG_PATH=/opt/amnezia/awg
SERVER_ENDPOINT={server_ip}:{server_config.get('PORT', '443')}
SERVER_PUBLIC_KEY={server_config.get('SERVER_PUBLIC_KEY', '')}
PRESHARED_KEY={server_config.get('PRESHARED_KEY', '')}

# Network Configuration
CLIENT_NETWORK={server_config.get('CLIENT_NETWORK', '10.8.1.0/24')}
CLIENT_IP_START={server_config.get('CLIENT_IP_START', '10.8.1.2')}

# AmneziaWG Parameters
JC={server_config.get('JC', '2')}
JMIN={server_config.get('JMIN', '10')}
JMAX={server_config.get('JMAX', '50')}
S1={server_config.get('S1', '105')}
S2={server_config.get('S2', '72')}
H1={server_config.get('H1', '1632458931')}
H2={server_config.get('H2', '1121810837')}
H3={server_config.get('H3', '697439987')}
H4={server_config.get('H4', '1960185003')}

# DNS Servers
DNS_SERVERS=1.1.1.1,1.0.0.1

# Database
DATABASE_PATH=data/database.db

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/bot.log
"""
    
    env_path = Path(__file__).parent / '.env'
    
    # Создаем резервную копию, если файл существует
    if env_path.exists():
        backup_path = Path(__file__).parent / '.env.backup'
        print(f"📦 Создание резервной копии: {backup_path}")
        import shutil
        shutil.copy(env_path, backup_path)
    
    with open(env_path, 'w') as f:
        f.write(env_content)
    
    print(f"✅ Файл .env создан: {env_path}")
    return True


def main():
    """Основная функция настройки"""
    print("=" * 60)
    print("🚀 AmneziaWG Config Bot - Автоматическая настройка")
    print("=" * 60)
    
    # Проверка Docker
    if not check_docker():
        sys.exit(1)
    
    # Проверка контейнера AmneziaWG
    if not check_amnezia_container():
        sys.exit(1)
    
    # Получение конфигурации сервера
    server_config = get_server_config()
    if not server_config:
        print("\n❌ Не удалось получить конфигурацию сервера")
        sys.exit(1)
    
    print("\n✅ Конфигурация сервера получена:")
    print(f"   - Публичный ключ: {server_config.get('SERVER_PUBLIC_KEY', 'N/A')[:20]}...")
    print(f"   - Порт: {server_config.get('PORT', 'N/A')}")
    print(f"   - Сеть клиентов: {server_config.get('CLIENT_NETWORK', 'N/A')}")
    print(f"   - Следующий IP: {server_config.get('CLIENT_IP_START', 'N/A')}")
    
    # Получение внешнего IP
    server_ip = get_server_ip()
    if not server_ip:
        server_ip = input("\n❓ Введите внешний IP адрес вашего сервера: ").strip()
        if not server_ip:
            print("❌ IP адрес обязателен")
            sys.exit(1)
    
    # Запрос данных от пользователя
    print("\n" + "=" * 60)
    print("📱 Настройка Telegram бота")
    print("=" * 60)
    
    print("\n1️⃣  Получите токен бота от @BotFather в Telegram:")
    print("   - Найдите @BotFather")
    print("   - Отправьте /newbot")
    print("   - Следуйте инструкциям")
    bot_token = input("\n❓ Введите токен бота: ").strip()
    
    if not bot_token:
        print("❌ Токен бота обязателен")
        sys.exit(1)
    
    print("\n2️⃣  Получите ваш Telegram ID от @userinfobot:")
    print("   - Найдите @userinfobot")
    print("   - Отправьте /start")
    admin_id = input("\n❓ Введите ваш Telegram ID (администратор): ").strip()
    
    if not admin_id or not admin_id.isdigit():
        print("❌ Telegram ID должен быть числом")
        sys.exit(1)
    
    print("\n3️⃣  Список разрешенных пользователей")
    print("   Введите Telegram ID пользователей через запятую")
    print(f"   Или просто нажмите Enter, чтобы добавить только себя ({admin_id})")
    users_input = input("\n❓ Telegram ID пользователей: ").strip()
    
    if not users_input:
        users = admin_id
    else:
        users = users_input
    
    # Создание .env файла
    if create_env_file(bot_token, admin_id, users, server_config, server_ip):
        print("\n" + "=" * 60)
        print("✅ Настройка завершена успешно!")
        print("=" * 60)
        print("\n📋 Следующие шаги:")
        print("   1. Проверьте файл .env")
        print("   2. Запустите бота: sudo systemctl start amneziabot")
        print("   3. Проверьте статус: sudo systemctl status amneziabot")
        print("   4. Отправьте /start вашему боту в Telegram")
        print("\n🎉 Готово! Бот настроен и готов к работе!")
    else:
        print("\n❌ Ошибка при создании .env файла")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Настройка прервана пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Непредвиденная ошибка: {e}")
        sys.exit(1)

