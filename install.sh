#!/bin/bash

# VK + Gemini Bot - Secure Edition
# Скрипт установки зависимостей и настройки окружения

set -e

echo "=== VK + Gemini Bot - Secure Edition ==="
echo "Установка зависимостей..."

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "Ошибка: Python 3 не найден. Установите Python 3.8 или выше."
    exit 1
fi

# Создание виртуального окружения
if [ ! -d "venv" ]; then
    echo "Создание виртуального окружения..."
    python3 -m venv venv
fi

# Активация виртуального окружения
echo "Активация виртуального окружения..."
source venv/bin/activate

# Обновление pip
echo "Обновление pip..."
pip install --upgrade pip

# Установка зависимостей
echo "Установка зависимостей из requirements.txt..."
pip install -r requirements.txt

# Копирование .env.example в .env
if [ ! -f ".env" ]; then
    echo "Создание файла .env из .env.example..."
    cp .env.example .env
    echo ""
    echo "!!! ВАЖНО: Отредактируйте файл .env и укажите ваши токены !!!"
    echo "- VK_TOKEN (получить в https://vk.com/apps?act=manage)"
    echo "- GEMINI_API_KEY (получить в https://makersuite.google.com/app/apikey)"
    echo "- ADMIN_PASSWORD (придумайте надежный пароль)"
    echo "- SECRET_KEY (случайная строка)"
fi

echo ""
echo "=== Установка завершена ==="
echo ""
echo "Для запуска бота выполните:"
echo "  source venv/bin/activate"
echo "  python bot.py"
echo ""
echo "Веб-панель будет доступна на http://localhost:5000"
