import os
import logging
from dotenv import load_dotenv
import vk_api
from vk_api.bot_helper import BotHelper
from openai import OpenAI

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Получение настроек из переменных окружения
VK_TOKEN = os.getenv('VK_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')

# Инициализация клиентов
vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()
client = OpenAI(api_key=OPENAI_API_KEY)

# Хранилище истории сообщений для каждого пользователя
user_history = {}

def get_llm_response(message, user_id):
    """Получение ответа от LLM модели"""
    if user_id not in user_history:
        user_history[user_id] = []
    
    # Добавляем сообщение пользователя в историю
    user_history[user_id].append({"role": "user", "content": message})
    
    # Ограничиваем историю последними 10 сообщениями
    if len(user_history[user_id]) > 10:
        user_history[user_id] = user_history[user_id][-10:]
    
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=user_history[user_id],
            max_tokens=1000,
            temperature=0.7
        )
        
        assistant_message = response.choices[0].message.content
        user_history[user_id].append({"role": "assistant", "content": assistant_message})
        
        return assistant_message
    except Exception as e:
        logger.error(f"Ошибка при запросе к LLM: {e}")
        return "Извините, произошла ошибка при обработке вашего запроса."

def main():
    """Основной цикл работы бота"""
    logger.info("Бот запущен...")
    
    # Использование long polling для получения сообщений
    lp = vk_api.longpoll.LongPoll(vk_session)
    
    for event in lp.listen():
        if event.type == vk_api.longpoll.LongpollEvent.MESSAGE_EVENT:
            try:
                user_id = event.obj['peer_id']
                message_text = event.obj.get('text', '')
                
                if message_text:
                    logger.info(f"Получено сообщение от {user_id}: {message_text}")
                    
                    # Получаем ответ от LLM
                    response = get_llm_response(message_text, user_id)
                    
                    # Отправляем ответ пользователю
                    vk.messages.send(
                        peer_id=user_id,
                        message=response,
                        random_id=0
                    )
                    
                    logger.info(f"Отправлен ответ пользователю {user_id}")
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке сообщения: {e}")

if __name__ == '__main__':
    main()
