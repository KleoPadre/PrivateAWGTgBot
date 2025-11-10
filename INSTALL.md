# Установка AmneziaWG Config Bot

Подробная пошаговая инструкция по установке бота.

## Требования

- ✅ Ubuntu Server (20.04+)
- ✅ Docker с установленным AmneziaWG
- ✅ Python 3.12+
- ✅ Root доступ к серверу

## Быстрая установка

### Шаг 1: Клонирование репозитория

```bash
cd /opt
git clone https://github.com/KleoPadre/PrivteAWGTgBot.git AmneziaBot
cd AmneziaBot
```

### Шаг 2: Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Шаг 3: Автоматическая настройка

```bash
python3 setup.py
```

Следуйте инструкциям скрипта:

1. **Токен бота** - получите от @BotFather:
   ```
   1. Найдите @BotFather в Telegram
   2. Отправьте /newbot
   3. Придумайте имя (например: My VPN Config Bot)
   4. Придумайте username (например: my_vpn_config_bot)
   5. Скопируйте токен (формат: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz)
   ```

2. **Telegram ID** - получите от @userinfobot:
   ```
   1. Найдите @userinfobot в Telegram
   2. Отправьте /start
   3. Скопируйте ваш ID (например: 123456789)
   ```

3. **Список пользователей** (опционально):
   ```
   - Введите ID через запятую: 123456789,987654321
   - Или просто нажмите Enter (добавится только ваш ID)
   ```

Скрипт автоматически:
- Найдет Docker контейнер AmneziaWG
- Извлечет все параметры конфигурации
- Определит внешний IP сервера
- Создаст файл `.env` со всеми настройками

### Шаг 4: Запуск бота

```bash
# Включить автозапуск
sudo systemctl enable amneziabot

# Запустить бота
sudo systemctl start amneziabot

# Проверить статус
sudo systemctl status amneziabot
```

### Шаг 5: Проверка работы

1. Найдите вашего бота в Telegram (по username, который указали в BotFather)
2. Отправьте команду `/start`
3. Вы должны увидеть клавиатуру с кнопками
4. Попробуйте получить конфиг, нажав на любую кнопку

## Что делает скрипт setup.py?

Скрипт автоматически собирает всю информацию из вашего AmneziaWG сервера:

### Проверки:
- ✅ Наличие Docker
- ✅ Запущен ли контейнер amnezia-awg
- ✅ Доступность конфигурации

### Извлекаемые параметры:

1. **Из конфигурации сервера** (`/opt/amnezia/awg/wg0.conf`):
   - SERVER_PUBLIC_KEY - публичный ключ сервера
   - PRESHARED_KEY - предварительный ключ
   - PORT - порт сервера (обычно 443)
   - CLIENT_NETWORK - сеть клиентов (10.8.1.0/24)
   - CLIENT_IP_START - следующий свободный IP
   - Параметры AmneziaWG (Jc, Jmin, Jmax, S1, S2, H1-H4)

2. **Внешний IP сервера**:
   - Автоматически определяется через ifconfig.me
   - Или запрашивается вручную, если автоопределение не сработало

3. **От пользователя**:
   - BOT_TOKEN - токен от BotFather
   - ADMIN_ID - ваш Telegram ID
   - USERS - список разрешенных пользователей

## Ручная настройка (если setup.py не работает)

Если автоматическая настройка не работает, выполните вручную:

### 1. Получите параметры из конфигурации:

```bash
docker exec amnezia-awg cat /opt/amnezia/awg/wg0.conf
```

### 2. Создайте .env файл:

```bash
cp .env.example .env
nano .env
```

### 3. Заполните параметры:

Найдите в выводе команды выше и скопируйте:
- `PrivateKey` → преобразуйте в публичный ключ для SERVER_PUBLIC_KEY
- `PresharedKey` → PRESHARED_KEY
- `ListenPort` → порт для SERVER_ENDPOINT
- `Jc`, `Jmin`, `Jmax`, `S1`, `S2`, `H1`-`H4` → соответствующие параметры

### 4. Получите публичный ключ из приватного:

```bash
PRIVATE_KEY="ваш_private_key_из_конфига"
echo $PRIVATE_KEY | docker exec -i amnezia-awg wg pubkey
```

## Troubleshooting

### setup.py не может найти контейнер

```bash
# Проверьте, что контейнер запущен
docker ps | grep amnezia

# Если не запущен - запустите
docker start amnezia-awg
```

### setup.py не может определить IP

```bash
# Узнайте ваш внешний IP вручную
curl ifconfig.me

# Укажите его в setup.py когда попросит
```

### Бот не запускается

```bash
# Проверьте логи
sudo journalctl -u amneziabot -n 50

# Проверьте .env файл
cat .env

# Убедитесь, что все параметры заполнены
```

## После установки

1. **Проверьте автозапуск**:
   ```bash
   sudo systemctl is-enabled amneziabot
   # Должно быть: enabled
   ```

2. **Просмотр логов**:
   ```bash
   tail -f /opt/AmneziaBot/logs/bot.log
   ```

3. **Добавление новых пользователей**:
   ```bash
   nano /opt/AmneziaBot/.env
   # Измените USERS, добавив новые ID через запятую
   sudo systemctl restart amneziabot
   ```

4. **Резервное копирование**:
   ```bash
   # Создайте бэкап базы данных и .env
   cp /opt/AmneziaBot/.env /opt/AmneziaBot/.env.backup
   cp /opt/AmneziaBot/data/database.db /opt/AmneziaBot/data/database.db.backup
   ```

## Безопасность

⚠️ **Важно:**
- Файл `.env` содержит токен бота - храните его в секрете
- Не коммитьте `.env` в git (уже в .gitignore)
- Регулярно проверяйте список USERS
- Используйте сильные пароли для сервера

## Поддержка

Если возникли проблемы:
1. Проверьте логи бота: `tail -f /opt/AmneziaBot/logs/bot.log`
2. Проверьте systemd логи: `sudo journalctl -u amneziabot -f`
3. Проверьте Docker: `docker logs amnezia-awg`
4. Прочитайте [QUICKSTART.md](QUICKSTART.md) и [README.md](README.md)

