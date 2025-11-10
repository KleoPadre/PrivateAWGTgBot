"""
Менеджер AmneziaWG для генерации и управления конфигурациями
"""
import asyncio
import json
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from src.config.settings import settings
from src.utils.logger import logger


class AmneziaWGManager:
    """Менеджер для работы с AmneziaWG"""
    
    def __init__(self):
        """Инициализация менеджера"""
        self.container = settings.AWG_CONTAINER
        self.config_path = settings.AWG_CONFIG_PATH
    
    async def _execute_command(self, command: str) -> Tuple[str, str, int]:
        """
        Выполнение команды через asyncio
        
        Args:
            command: Команда для выполнения
            
        Returns:
            Tuple[str, str, int]: (stdout, stderr, return_code)
        """
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            return (
                stdout.decode('utf-8').strip(),
                stderr.decode('utf-8').strip(),
                process.returncode
            )
        except Exception as e:
            logger.error(f"Ошибка выполнения команды '{command}': {e}")
            raise
    
    async def generate_keypair(self) -> Tuple[str, str]:
        """
        Генерация пары ключей для клиента
        
        Returns:
            Tuple[str, str]: (private_key, public_key)
        """
        # Генерируем приватный ключ
        private_cmd = f"docker exec {self.container} wg genkey"
        private_key, stderr, code = await self._execute_command(private_cmd)
        
        if code != 0:
            raise Exception(f"Ошибка генерации приватного ключа: {stderr}")
        
        # Генерируем публичный ключ из приватного
        public_cmd = f"echo '{private_key}' | docker exec -i {self.container} wg pubkey"
        public_key, stderr, code = await self._execute_command(public_cmd)
        
        if code != 0:
            raise Exception(f"Ошибка генерации публичного ключа: {stderr}")
        
        logger.info("Пара ключей успешно сгенерирована")
        return private_key, public_key
    
    async def get_next_available_ip(self) -> str:
        """
        Получение следующего свободного IP адреса
        
        Returns:
            str: Свободный IP адрес
        """
        # Читаем текущую конфигурацию
        read_cmd = f"docker exec {self.container} cat {self.config_path}/wg0.conf"
        config_content, stderr, code = await self._execute_command(read_cmd)
        
        if code != 0:
            logger.error(f"Ошибка чтения конфигурации: {stderr}")
            # Если не можем прочитать, используем стартовый IP
            return settings.CLIENT_IP_START
        
        # Парсим используемые IP
        used_ips = []
        for line in config_content.split('\n'):
            if line.strip().startswith('AllowedIPs'):
                ip_with_mask = line.split('=')[1].strip()
                ip = ip_with_mask.split('/')[0]
                # Извлекаем последний октет
                last_octet = int(ip.split('.')[-1])
                used_ips.append(last_octet)
        
        # Находим следующий свободный IP
        network_base = '.'.join(settings.CLIENT_IP_START.split('.')[:-1])
        start_octet = int(settings.CLIENT_IP_START.split('.')[-1])
        
        for i in range(start_octet, 255):
            if i not in used_ips:
                next_ip = f"{network_base}.{i}"
                logger.info(f"Найден свободный IP: {next_ip}")
                return next_ip
        
        raise Exception("Нет доступных IP адресов в сети")
    
    async def add_peer_to_server(
        self,
        client_public_key: str,
        client_ip: str,
        client_name: str
    ) -> None:
        """
        Добавление peer в конфигурацию сервера
        
        Args:
            client_public_key: Публичный ключ клиента
            client_ip: IP адрес клиента
            client_name: Имя клиента
        """
        # Формируем секцию peer
        peer_config = f"""
[Peer]
PublicKey = {client_public_key}
PresharedKey = {settings.PRESHARED_KEY}
AllowedIPs = {client_ip}/32
"""
        
        # Добавляем peer в конфигурацию
        append_cmd = f"docker exec {self.container} sh -c 'echo \"{peer_config}\" >> {self.config_path}/wg0.conf'"
        stdout, stderr, code = await self._execute_command(append_cmd)
        
        if code != 0:
            raise Exception(f"Ошибка добавления peer в конфигурацию: {stderr}")
        
        # Обновляем clientsTable
        await self._update_clients_table(client_public_key, client_ip, client_name)
        
        # Применяем изменения
        await self._apply_config_changes()
        
        logger.info(f"Peer добавлен: {client_name} ({client_ip})")
    
    async def _update_clients_table(
        self,
        client_public_key: str,
        client_ip: str,
        client_name: str
    ) -> None:
        """
        Обновление таблицы клиентов в JSON формате
        
        Args:
            client_public_key: Публичный ключ клиента
            client_ip: IP адрес клиента
            client_name: Имя клиента
        """
        # Читаем текущую таблицу клиентов
        read_cmd = f"docker exec {self.container} cat {self.config_path}/clientsTable"
        clients_json, stderr, code = await self._execute_command(read_cmd)
        
        clients = []
        if code == 0 and clients_json:
            try:
                clients = json.loads(clients_json)
            except json.JSONDecodeError:
                logger.warning("Не удалось распарсить clientsTable, создаем новый")
                clients = []
        
        # Добавляем нового клиента (формат как в AmneziaVPN приложении)
        from datetime import datetime
        new_client = {
            "clientId": client_public_key,
            "userData": {
                "clientName": client_name,
                "creationDate": datetime.now().strftime("%a %b %d %H:%M:%S %Y")
            }
        }
        clients.append(new_client)
        
        # Записываем обратно
        clients_json_str = json.dumps(clients, indent=4, ensure_ascii=False)
        
        # Записываем через временный файл для атомарной операции
        import tempfile
        import os
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
        temp_file.write(clients_json_str)
        temp_file.close()
        
        # Копируем файл в контейнер
        copy_cmd = f"docker cp {temp_file.name} {self.container}:{self.config_path}/clientsTable"
        stdout, stderr, code = await self._execute_command(copy_cmd)
        
        # Удаляем временный файл
        os.unlink(temp_file.name)
        
        if code != 0:
            logger.error(f"Ошибка обновления clientsTable: {stderr}")
        else:
            logger.info(f"clientsTable обновлен: добавлен {client_name}")
    
    async def _apply_config_changes(self) -> None:
        """Применение изменений конфигурации WireGuard"""
        # Применяем изменения через wg syncconf
        sync_cmd = f"docker exec {self.container} sh -c 'wg syncconf wg0 <(wg-quick strip {self.config_path}/wg0.conf)'"
        stdout, stderr, code = await self._execute_command(sync_cmd)
        
        if code != 0:
            logger.warning(f"Не удалось применить через syncconf: {stderr}, пробуем альтернативный метод")
            # Альтернативный метод - просто применяем setconf
            alt_cmd = f"docker exec {self.container} wg setconf wg0 {self.config_path}/wg0.conf"
            stdout, stderr, code = await self._execute_command(alt_cmd)
            
            if code != 0:
                logger.error(f"Не удалось применить изменения: {stderr}")
            else:
                logger.info("Изменения применены через setconf")
        else:
            logger.info("Изменения успешно применены через syncconf")


# Глобальный экземпляр менеджера
awg_manager = AmneziaWGManager()

