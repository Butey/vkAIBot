import os
import logging
import re
import hashlib
from datetime import datetime
from urllib.parse import urlparse
from flask import Flask, request, render_template_string, session, redirect, url_for, flash
from werkzeug.utils import secure_filename
import vk_api
from vk_api import VkApi
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.upload import VkUpload
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import requests
from dotenv import load_dotenv
from functools import wraps
from openai import OpenAI

# Загрузка переменных окружения
load_dotenv()

# ==================== КОНФИГУРАЦИЯ ====================
VK_TOKEN = os.getenv('VK_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
NVIDIA_API_KEY = os.getenv('NVIDIA_API_KEY')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(24).hex())
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
DEFAULT_MODEL = os.getenv('DEFAULT_MODEL', 'google/gemini-1.5-flash')

# Доверенные хосты для загрузки изображений (ВК)
TRUSTED_HOSTS = [
    'vk.com',
    '*.vk.com',
    'userpic.vk.ru',
    '*.userpic.vk.ru',
    'sun1-*.userpic.vk.ru',
    'sun2-*.userpic.vk.ru',
    'sun3-*.userpic.vk.ru',
    'sun4-*.userpic.vk.ru',
    'sun5-*.userpic.vk.ru',
    'sun6-*.userpic.vk.ru',
    'sun7-*.userpic.vk.ru',
    'sun8-*.userpic.vk.ru',
    'sun9-*.userpic.vk.ru'
]

# ==================== БЕЗОПАСНЫЙ ФИЛЬТР ДЛЯ ЛОГОВ ====================
class SecureFilter(logging.Filter):
    """Фильтр для маскировки токенов в логах"""
    
    def __init__(self):
        super().__init__()
        self.patterns = [
            (r'vk_token[=:]\s*[A-Za-z0-9_-]+', 'vk_token=***'),
            (r'api_key[=:]\s*[A-Za-z0-9_-]+', 'api_key=***'),
            (r'GEMINI_API_KEY[=:]\s*[A-Za-z0-9_-]+', 'GEMINI_API_KEY=***'),
            (r'NVIDIA_API_KEY[=:]\s*[A-Za-z0-9_-]+', 'NVIDIA_API_KEY=***'),
            (r'ADMIN_PASSWORD[=:]\s*[A-Za-z0-9_-]+', 'ADMIN_PASSWORD=***'),
            (r'session[=:]\s*[A-Za-z0-9_-]+', 'session=***'),
        ]
    
    def filter(self, record):
        if isinstance(record.msg, str):
            for pattern, replacement in self.patterns:
                record.msg = re.sub(pattern, replacement, record.msg, flags=re.IGNORECASE)
        if record.args:
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    for pattern, replacement in self.patterns:
                        arg = re.sub(pattern, replacement, arg, flags=re.IGNORECASE)
                new_args.append(arg)
            record.args = tuple(new_args)
        return True

# Настройка логирования с безопасным фильтром
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.addFilter(SecureFilter())

# ==================== ИНИЦИАЛИЗАЦИЯ КЛИЕНТОВ ====================
try:
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    upload = VkUpload(vk_session)
    logger.info("VK API инициализирован успешно")
except Exception as e:
    logger.error(f"Ошибка инициализации VK API: {e}")
    vk = None
    upload = None

try:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("Google Gemini инициализирован успешно")
except Exception as e:
    logger.error(f"Ошибка инициализации Google Gemini: {e}")
    gemini_model = None

# Инициализация NVIDIA NIM клиента (OpenAI-compatible API)
nvidia_client = None
if NVIDIA_API_KEY:
    try:
        nvidia_client = OpenAI(
            api_key=NVIDIA_API_KEY,
            base_url="https://integrate.api.nvidia.com/v1"
        )
        logger.info("NVIDIA NIM API инициализирован успешно")
    except Exception as e:
        logger.error(f"Ошибка инициализации NVIDIA NIM API: {e}")
        nvidia_client = None
else:
    logger.warning("NVIDIA_API_KEY не указан. Модели NVIDIA будут недоступны.")

# Список доступных моделей NVIDIA NIM с категориями
NVIDIA_MODELS = [
    "google/gemma-7b",
    "meta/llama3-8b-instruct",
    "meta/llama3-70b-instruct",
    "mistralai/mistral-large",
    "mistralai/mixtral-8x7b-instruct-v0.1",
    "microsoft/phi-3-mini-128k-instruct",
    "microsoft/phi-3-medium-128k-instruct",
    "nvidia/nemotron-4-340b-instruct",
    "databricks/dbrx-instruct",
    "snowflake/arctic",
    "ibm/granite-34b-code-instruct",
    "google/codegemma-7b",
    "google/paligemma",
    "adept/cosmos-1.0",
    "nv-mistralai/mistral-nemo-12b-instruct",
    "qwen/qwen2-7b-instruct",
    "qwen/qwen2-72b-instruct",
    "aisingapore/sea-lion-7b-instruct",
    "thudm/chatglm3-6b",
    "zyphra/zamba-7b-instruct",
    "meta/llama-3.1-8b-instruct",
    "meta/llama-3.1-70b-instruct",
    "meta/llama-3.1-405b-instruct",
    "google/gemma-2-9b-it",
    "google/gemma-2-27b-it",
    "google/gemma-2b-it",
    "google/codegemma-1.1-7b",
    "google/recurrentgemma-2b",
    "mistralai/mistral-7b-instruct-v0.2",
    "mistralai/mistral-7b-instruct-v0.3",
    "mistralai/codestral-22b-instruct-v0.1",
    "mistralai/mathstral-7b-v0.1",
    "nvidia/nemotron-mini-4b-instruct",
    "nvidia/userraya-llama3-70b",
    "baichuan-inc/baichuan2-13b-chat",
    "writer/palmyra-med-70b-32k",
    "writer/palmyra-fin-70b-32k",
    "salesforce/llama-xlam-8b",
    "upstage/solar-10.7b-instruct",
    "seallms/seallm-7b-v2.5",
    "rakuten/rakutenai-7b-chat",
    "aisingapore/sea-lion-7b-instruct",
]

# Категории моделей для разных задач
MODEL_CATEGORIES = {
    'code': [
        'ibm/granite-34b-code-instruct',
        'google/codegemma-7b',
        'google/codegemma-1.1-7b',
        'mistralai/codestral-22b-instruct-v0.1',
    ],
    'math': [
        'mistralai/mathstral-7b-v0.1',
        'meta/llama-3.1-405b-instruct',
        'meta/llama-3.1-70b-instruct',
        'nvidia/nemotron-4-340b-instruct',
    ],
    'creative': [
        'meta/llama-3.1-405b-instruct',
        'mistralai/mistral-large',
        'meta/llama3-70b-instruct',
        'google/gemma-2-27b-it',
    ],
    'fast': [
        'microsoft/phi-3-mini-128k-instruct',
        'meta/llama3-8b-instruct',
        'google/gemma-2b-it',
        'nvidia/nemotron-mini-4b-instruct',
    ],
    'vision': [
        'google/paligemma',
        'adept/cosmos-1.0',
    ],
    'general': [
        'meta/llama-3.1-70b-instruct',
        'mistralai/mixtral-8x7b-instruct-v0.1',
        'google/gemma-2-9b-it',
        'qwen/qwen2-72b-instruct',
    ],
}

def detect_task_type(message, has_image=False):
    """
    Определение типа задачи по сообщению пользователя
    Возвращает: 'code', 'math', 'creative', 'vision', 'general'
    """
    message_lower = message.lower() if message else ''
    
    # Если есть изображение - задача на анализ vision
    if has_image:
        return 'vision'
    
    # Ключевые слова для кода
    code_keywords = ['код', 'программ', 'скрипт', 'функци', 'класс', 'дебаг', 'ошибк', 
                     'python', 'javascript', 'java', 'c++', 'html', 'css', 'sql',
                     'напиши код', 'создай функцию', 'исправь ошибку', 'рефактор',
                     'import', 'def ', 'class ', 'function', 'var ', 'let ', 'const ']
    
    # Ключевые слова для математики
    math_keywords = ['реши', 'уравнени', 'вычисли', 'посчитай', 'математик', 'алгебр',
                     'геометр', 'интеграл', 'производн', 'формула', 'числ', 'калькулятор',
                     '√', '∑', '∫', 'π', '°', 'радиан', 'синус', 'косинус', 'тангенс']
    
    # Ключевые слова для креативных задач
    creative_keywords = ['придумай', 'напиши стих', 'рассказ', 'историю', 'сценарий',
                         'креатив', 'творчеств', 'поэзия', 'стихотворени', 'песню',
                         'описание', 'маркетинг', 'копирайт', 'слоган', 'нейминг']
    
    # Проверка на код
    code_score = sum(1 for kw in code_keywords if kw in message_lower)
    if code_score >= 1 or any(x in message_lower for x in ['```', 'import ', 'def ', 'function']):
        return 'code'
    
    # Проверка на математику
    math_score = sum(1 for kw in math_keywords if kw in message_lower)
    if math_score >= 2 or any(x in message_lower for x in ['=', '+', '-', '*', '/', '²', '³']):
        return 'math'
    
    # Проверка на креатив
    creative_score = sum(1 for kw in creative_keywords if kw in message_lower)
    if creative_score >= 1:
        return 'creative'
    
    # Проверка на короткий быстрый вопрос
    if len(message_lower.split()) <= 3:
        return 'fast'
    
    # По умолчанию - общая задача
    return 'general'

def get_optimal_model(task_type, has_image=False):
    """
    Получение оптимальной модели для типа задачи
    """
    # Для изображений всегда используем Gemini или специализированные vision модели
    if has_image and gemini_model:
        return 'google/gemini-1.5-flash'
    
    # Получаем список моделей для категории
    models = MODEL_CATEGORIES.get(task_type, MODEL_CATEGORIES['general'])
    
    # Выбираем первую доступную модель из списка
    for model in models:
        if model in NVIDIA_MODELS and nvidia_client:
            return model
    
    # Fallback на модель по умолчанию
    return DEFAULT_MODEL

# ==================== ФУНКЦИИ БЕЗОПАСНОСТИ ====================
def is_safe_url(url):
    """Проверка безопасности URL для загрузки изображений"""
    try:
        parsed = urlparse(url)
        
        # Проверка схемы (только HTTPS)
        if parsed.scheme != 'https':
            logger.warning(f"Небезопасная схема URL: {parsed.scheme}")
            return False
        
        # Проверка хоста на наличие в доверенном списке
        host = parsed.netloc.lower()
        for trusted in TRUSTED_HOSTS:
            if trusted.startswith('*.'):
                domain = trusted[2:]
                if host.endswith(domain) or host == domain[1:]:
                    return True
            elif host == trusted:
                return True
        
        logger.warning(f"Недоверенный хост: {host}")
        return False
    except Exception as e:
        logger.error(f"Ошибка проверки URL: {e}")
        return False

def escape_html(text):
    """Экранирование HTML для предотвращения XSS"""
    if not isinstance(text, str):
        return str(text)
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#x27;'))

def allowed_file(filename):
    """Проверка расширения файла"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_csrf_token():
    """Генерация CSRF токена"""
    return hashlib.sha256(os.urandom(32)).hexdigest()

def validate_csrf_token(token):
    """Валидация CSRF токена"""
    if not token or not session.get('csrf_token'):
        return False
    return token == session.get('csrf_token')

# ==================== FLASK ПРИЛОЖЕНИЕ ====================
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Хранилище статистики
stats = {
    'total_messages': 0,
    'total_images': 0,
    'active_users': set(),
    'errors': []
}

# ==================== ДЕКОРАТОРЫ ====================
def login_required(f):
    """Декоратор для защиты маршрутов аутентификацией"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Требуется авторизация', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def csrf_protect(f):
    """Декоратор для защиты от CSRF атак"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
            if not validate_csrf_token(token):
                flash('Неверный CSRF токен', 'error')
                return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== МАРШРУТЫ FLASK ====================
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Маршрут входа в панель администратора"""
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        csrf_token = request.form.get('csrf_token', '')
        
        if not validate_csrf_token(csrf_token):
            flash('Неверный CSRF токен', 'error')
            return render_template_string(LOGIN_TEMPLATE, csrf_token=generate_csrf_token())
        
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['csrf_token'] = generate_csrf_token()
            flash('Успешный вход', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Неверный пароль', 'error')
    
    csrf_token = generate_csrf_token()
    session['csrf_token'] = csrf_token
    return render_template_string(LOGIN_TEMPLATE, csrf_token=csrf_token)

@app.route('/logout')
def logout():
    """Маршрут выхода"""
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    """Панель администратора"""
    csrf_token = session.get('csrf_token', generate_csrf_token())
    return render_template_string(DASHBOARD_TEMPLATE, 
                                  stats=stats, 
                                  escape=escape_html,
                                  csrf_token=csrf_token)

@app.route('/logs')
@login_required
def logs():
    """Просмотр логов (последние 100 записей)"""
    csrf_token = session.get('csrf_token', generate_csrf_token())
    recent_errors = stats['errors'][-100:] if stats['errors'] else []
    return render_template_string(LOGS_TEMPLATE, 
                                  errors=recent_errors,
                                  escape=escape_html,
                                  csrf_token=csrf_token)

def get_nvidia_response(message, user_id, model_name=None):
    """Получение ответа от NVIDIA NIM API"""
    if not nvidia_client:
        return "NVIDIA API не инициализирован. Проверьте NVIDIA_API_KEY."
    
    try:
        stats['active_users'].add(user_id)
        stats['total_messages'] += 1
        
        # Используем модель по умолчанию или указанную
        model = model_name if model_name and model_name in NVIDIA_MODELS else DEFAULT_MODEL
        
        # Если модель не из списка NVIDIA, пробуем использовать её напрямую
        if model not in NVIDIA_MODELS and '/' in model:
            pass  # Разрешаем кастомные модели в формате provider/model
        
        response = nvidia_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Ты полезный ассистент в ВКонтакте. Отвечай на русском языке кратко и по делу."},
                {"role": "user", "content": message}
            ],
            temperature=0.7,
            max_tokens=1024,
            top_p=0.9
        )
        
        return response.choices[0].message.content
    except Exception as e:
        error_msg = f"Ошибка NVIDIA NIM для пользователя {user_id}: {str(e)}"
        logger.error(error_msg)
        stats['errors'].append({
            'timestamp': datetime.now().isoformat(),
            'message': error_msg
        })
        return "Извините, произошла ошибка при обработке вашего запроса через NVIDIA API."

def get_llm_response(message, user_id, image_data=None, model_name=None):
    """Универсальная функция получения ответа от LLM (Gemini или NVIDIA)"""
    # Определяем, какую модель использовать
    use_nvidia = model_name and (model_name in NVIDIA_MODELS or '/' in model_name)
    
    if use_nvidia and nvidia_client:
        return get_nvidia_response(message, user_id, model_name)
    elif gemini_model:
        return get_gemini_response(message, user_id, image_data)
    else:
        return "LLM сервисы не настроены. Проверьте API ключи."

# ==================== LLM ИНТЕГРАЦИЯ ====================
def get_gemini_response(message, user_id, image_data=None):
    """Получение ответа от Google Gemini с поддержкой изображений"""
    try:
        stats['active_users'].add(user_id)
        stats['total_messages'] += 1
        
        if image_data:
            stats['total_images'] += 1
            # Мультимодальный запрос с изображением
            response = gemini_model.generate_content([
                "Проанализируй это изображение и ответь на вопрос пользователя.",
                image_data,
                message
            ], safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            })
        else:
            # Текстовый запрос
            response = gemini_model.generate_content([
                "Ты полезный ассистент в ВКонтакте. Отвечай на русском языке кратко и по делу.",
                message
            ], safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            })
        
        return response.text
    except Exception as e:
        error_msg = f"Ошибка Gemini для пользователя {user_id}: {str(e)}"
        logger.error(error_msg)
        stats['errors'].append({
            'timestamp': datetime.now().isoformat(),
            'message': error_msg
        })
        return "Извините, произошла ошибка при обработке вашего запроса."

def download_image_secure(url):
    """Безопасная загрузка изображения с проверкой URL"""
    if not is_safe_url(url):
        logger.warning(f"Попытка загрузки с небезопасного URL: {url}")
        return None
    
    try:
        response = requests.get(url, timeout=10, allow_redirects=False)
        if response.status_code == 200 and 'image' in response.headers.get('Content-Type', ''):
            return response.content
        logger.warning(f"Не удалось загрузить изображение: {url}")
        return None
    except Exception as e:
        logger.error(f"Ошибка загрузки изображения: {e}")
        return None

# ==================== ОСНОВНОЙ ЦИКЛ БОТА ====================
def process_message(event):
    """Обработка входящего сообщения с автоматическим выбором модели"""
    try:
        user_id = event.obj.message.get('peer_id')
        message_text = event.obj.message.get('text', '')
        attachments = event.obj.message.get('attachments', [])
        
        if not user_id:
            return
        
        logger.info(f"Получено сообщение от {user_id}: {message_text[:100]}...")
        
        # Обработка изображений
        image_data = None
        for attachment in attachments:
            if attachment.get('type') == 'photo':
                photo = attachment.get('photo', {})
                # Получаем URL изображения максимального размера
                image_url = photo.get('sizes', [-1])[-1].get('url')
                
                if image_url:
                    logger.info(f"Загрузка изображения: {image_url}")
                    image_data = download_image_secure(image_url)
                    if image_data:
                        logger.info("Изображение загружено успешно")
                    break
        
        # Определяем тип задачи и выбираем оптимальную модель
        has_image = image_data is not None
        task_type = detect_task_type(message_text, has_image)
        model_name = get_optimal_model(task_type, has_image)
        
        logger.info(f"Тип задачи: {task_type}, выбрана модель: {model_name}")
        
        # Получаем ответ от LLM
        if message_text or image_data:
            query = message_text if message_text else "Опиши это изображение"
            response = get_llm_response(query, user_id, image_data, model_name)
            
            # Добавляем информацию о выбранной модели (опционально, можно убрать)
            # response = f"[{model_name.split('/')[-1]}] {response}"
            
            # Отправляем ответ пользователю
            if vk:
                vk.messages.send(
                    peer_id=user_id,
                    message=response,
                    random_id=0
                )
                logger.info(f"Отправлен ответ пользователю {user_id} (модель: {model_name})")
        
    except Exception as e:
        error_msg = f"Ошибка обработки сообщения: {str(e)}"
        logger.error(error_msg)
        stats['errors'].append({
            'timestamp': datetime.now().isoformat(),
            'message': error_msg
        })

def main():
    """Основной цикл работы бота"""
    logger.info("Бот запущен в безопасном режиме...")
    
    if not vk:
        logger.error("VK API не инициализирован. Проверьте токен.")
        return
    
    # Использование Bot Long Polling для получения сообщений
    group_id = int(vk_session.method('groups.getById')[0]['group_id'])
    lp = VkBotLongPoll(vk_session, group_id)
    
    for event in lp.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            process_message(event)

# ==================== HTML ШАБЛОНЫ ====================
LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Вход - VK Gemini Bot</title>
    <style>
        body { font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background: #f0f2f5; }
        .login-form { background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); width: 300px; }
        h2 { text-align: center; color: #333; }
        input[type="password"] { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
        button { width: 100%; padding: 10px; background: #0077FF; color: white; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #0055cc; }
        .flash { padding: 10px; margin-bottom: 10px; border-radius: 4px; }
        .error { background: #ffebee; color: #c62828; }
        .success { background: #e8f5e9; color: #2e7d32; }
        .info { background: #e3f2fd; color: #1565c0; }
    </style>
</head>
<body>
    <div class="login-form">
        <h2>VK Gemini Bot</h2>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash {{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        <form method="POST">
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
            <input type="password" name="password" placeholder="Пароль" required>
            <button type="submit">Войти</button>
        </form>
    </div>
</body>
</html>
'''

DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Панель управления - VK Gemini Bot</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f0f2f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 20px; }
        .stat-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .stat-value { font-size: 2em; font-weight: bold; color: #0077FF; }
        .stat-label { color: #666; margin-top: 5px; }
        .nav-links a { margin-right: 15px; color: #0077FF; text-decoration: none; }
        .nav-links a:hover { text-decoration: underline; }
        .flash { padding: 10px; margin-bottom: 10px; border-radius: 4px; }
        .error { background: #ffebee; color: #c62828; }
        .success { background: #e8f5e9; color: #2e7d32; }
        .info { background: #e3f2fd; color: #1565c0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>VK Gemini Bot - Панель управления</h1>
            <div class="nav-links">
                <a href="/">Статистика</a>
                <a href="/logs">Логи</a>
                <a href="/logout">Выход</a>
            </div>
        </div>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash {{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{{ stats.total_messages }}</div>
                <div class="stat-label">Всего сообщений</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ stats.total_images }}</div>
                <div class="stat-label">Обработано изображений</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ stats.active_users|length }}</div>
                <div class="stat-label">Активных пользователей</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ stats.errors|length }}</div>
                <div class="stat-label">Ошибок</div>
            </div>
        </div>
    </div>
</body>
</html>
'''

LOGS_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Логи - VK Gemini Bot</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f0f2f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .nav-links a { margin-right: 15px; color: #0077FF; text-decoration: none; }
        .nav-links a:hover { text-decoration: underline; }
        .log-table { width: 100%; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .log-table th, .log-table td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
        .log-table th { background: #f8f9fa; font-weight: bold; }
        .error-row { background: #ffebee; }
        .timestamp { color: #666; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Логи ошибок</h1>
            <div class="nav-links">
                <a href="/">Статистика</a>
                <a href="/logs">Логи</a>
                <a href="/logout">Выход</a>
            </div>
        </div>
        
        {% if errors %}
        <table class="log-table">
            <thead>
                <tr>
                    <th>Время</th>
                    <th>Ошибка</th>
                </tr>
            </thead>
            <tbody>
                {% for error in errors %}
                <tr class="error-row">
                    <td class="timestamp">{{ escape(error.timestamp) }}</td>
                    <td>{{ escape(error.message) }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p>Ошибок не обнаружено</p>
        {% endif %}
    </div>
</body>
</html>
'''

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    import threading
    
    # Запуск Flask в отдельном потоке
    def run_flask():
        app.run(host='0.0.0.0', port=5000, debug=False)
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("Веб-панель доступна на http://0.0.0.0:5000")
    
    # Запуск основного цикла бота
    main()
