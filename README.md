# VK + Gemini Bot (Secure Edition)

Безопасный бот для ВКонтакте с интеграцией Google Gemini для мультимодального анализа изображений и текста.

## Особенности

- 🤖 Интеграция с **Google Gemini 1.5 Flash**
- 🖼️ **Мультимодальный анализ** изображений и текста
- 🔒 **Secure Edition** с исправленными уязвимостями:
  - XSS защита
  - Аутентификация в веб-панели
  - Защита от Path Traversal
  - SSRF защита
  - Маскировка токенов в логах
  - CSRF защита
- 📊 Веб-панель администратора со статистикой
- 📝 Логирование ошибок

## Структура проекта

```
.
├── bot.py              # Основной код бота
├── requirements.txt    # Зависимости Python
├── .env.example        # Шаблон переменных окружения
├── install.sh          # Скрипт установки
├── SECURITY_FIXES.md   # Документация по безопасности
└── README.md           # Этот файл
```

## Быстрый старт

### 1. Клонирование или создание файлов

Создайте файлы согласно структуре выше или склонируйте репозиторий.

### 2. Настройка переменных окружения

```bash
cp .env.example .env
nano .env  # Или любой другой редактор
```

Заполните `.env` своими данными:

```ini
VK_TOKEN=your_vk_token_here
GEMINI_API_KEY=your_gemini_api_key_here
ADMIN_PASSWORD=your_secure_password_here
SECRET_KEY=your_random_secret_key_here
```

**Где получить токены:**
- **VK_TOKEN**: https://vk.com/apps?act=manage (создайте Standalone-приложение)
- **GEMINI_API_KEY**: https://makersuite.google.com/app/apikey

### 3. Установка зависимостей

#### Вариант A: Автоматическая установка (Linux/Mac)

```bash
chmod +x install.sh
./install.sh
```

#### Вариант B: Ручная установка

```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Запуск бота

```bash
source venv/bin/activate  # Если не активировано
python bot.py
```

### 5. Доступ к веб-панели

Откройте в браузере: **http://ваш-ip:5000**

Введите пароль, указанный в `ADMIN_PASSWORD`.

## Функционал

### Для пользователей ВКонтакте

- Отправка текстовых сообщений боту
- Отправка изображений для анализа
- Получение ответов от Google Gemini
- Контекстная память (последние 10 сообщений)

### Для администраторов

- **Панель статистики** (`/`):
  - Всего сообщений
  - Обработано изображений
  - Активных пользователей
  - Количество ошибок

- **Просмотр логов** (`/logs`):
  - Последние 100 ошибок
  - Временные метки
  - Маскированные токены

- **Управление сессией** (`/login`, `/logout`)

## Безопасность

Подробная информация об исправленных уязвимостях в файле [SECURITY_FIXES.md](SECURITY_FIXES.md).

### Основные меры защиты:

1. **XSS защита**: Все данные экранируются перед выводом
2. **Аутентификация**: Обязательный вход по паролю
3. **SSRF защита**: Проверка URL изображений на доверенные хосты
4. **CSRF защита**: Токены для всех форм
5. **Маскировка токенов**: Секретные данные скрыты в логах
6. **Ограничение размера файлов**: Максимум 16MB

## Рекомендации по развертыванию

1. **Используйте HTTPS** в продакшене через nginx или Apache
2. **Измените ADMIN_PASSWORD** на сложный пароль
3. **Настройте firewall** для порта 5000
4. **Регулярно обновляйте зависимости**: `pip install --upgrade -r requirements.txt`
5. **Защитите .env файл**: `chmod 600 .env`
6. **Не коммитьте .env** в git (уже в .gitignore)

## Запуск в фоновом режиме

### Через systemd (рекомендуется для продакшена)

Создайте файл `/etc/systemd/system/vk-gemini-bot.service`:

```ini
[Unit]
Description=VK Gemini Bot
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/bot
Environment="PATH=/path/to/bot/venv/bin"
ExecStart=/path/to/bot/venv/bin/python bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Запустите:

```bash
sudo systemctl daemon-reload
sudo systemctl enable vk-gemini-bot
sudo systemctl start vk-gemini-bot
```

## Устранение неполадок

### Бот не запускается

- Проверьте правильность токенов в `.env`
- Убедитесь, что все зависимости установлены: `pip install -r requirements.txt`
- Проверьте логи на наличие ошибок

### Веб-панель недоступна

- Убедитесь, что порт 5000 не занят: `lsof -i :5000`
- Проверьте firewall: `sudo ufw allow 5000`

### Ошибки при загрузке изображений

- Проверьте, что URL изображения доступен
- Убедитесь, что изображение не превышает 16MB

## Лицензия

MIT License

## Поддержка

При возникновении проблем создайте issue в репозитории.
