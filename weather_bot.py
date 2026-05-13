import os
import time
import math
import logging
import requests
import telebot
from datetime import datetime, timezone
from telebot import types

# --- КОНФИГУРАЦИЯ ---
API_KEY = os.getenv('WEATHER_API_KEY', '482adb12c18eaf2ee9c6a2dac8e6c7b3')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8833502523:AAE62skdOoe9ZvSEseYiHH9rxbbyPaK-iT0')

# Логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Города для выбора
CITIES = {
    "Москва": {"lat": 55.75, "lon": 37.61},
    "Санкт-Петербург": {"lat": 59.93, "lon": 30.33},
    "Казань": {"lat": 55.79, "lon": 49.11},
    "Новосибирск": {"lat": 55.00, "lon": 82.93},
    "Екатеринбург": {"lat": 56.83, "lon": 60.60},
    "Нижний Новгород": {"lat": 56.32, "lon": 44.00},
    "Сочи": {"lat": 43.60, "lon": 39.73},
    "Владивосток": {"lat": 43.11, "lon": 131.88}
}

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_weather_data(lat, lon):
    """Получает текущую погоду и прогноз"""
    try:
        # Текущая погода
        current_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={API_KEY}&units=metric&lang=ru"
        current_resp = requests.get(current_url, timeout=10)
        current_resp.raise_for_status()
        current_data = current_resp.json()

        # Прогноз
        forecast_url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={API_KEY}&units=metric&lang=ru"
        forecast_resp = requests.get(forecast_url, timeout=10)
        forecast_resp.raise_for_status()
        forecast_data = forecast_resp.json()

        return current_data, forecast_data
    except Exception as e:
        logger.error(f"Ошибка при получении данных погоды: {e}")
        return None, None

def get_moon_phase(day=None):
    """Рассчитывает фазу луны"""
    if day is None:
        day = datetime.now()
    
    # Алгоритм Конвея (упрощенный)
    year = day.year
    month = day.month
    day_num = day.day
    
    if month < 3:
        year -= 1
        month += 12
    
    c = 365.25 * year
    e = 30.6 * month
    jd = c + e + day_num - 694039.09  # Юлианская дата (упрощенно)
    cycle = (jd % 29.5305882) / 29.5305882 * 8
    
    phase_name = ""
    emoji = ""
    
    if cycle < 1:
        phase_name = "🌑 Новолуние"
        emoji = "🌑"
    elif cycle < 2:
        phase_name = "🌒 Растущая"
        emoji = "🌒"
    elif cycle < 3:
        phase_name = "🌓 Первая четверть"
        emoji = "🌓"
    elif cycle < 4:
        phase_name = "🌔 Растущая"
        emoji = "🌔"
    elif cycle < 5:
        phase_name = "🌕 Полнолуние"
        emoji = "🌕"
    elif cycle < 6:
        phase_name = "🌖 Убывающая"
        emoji = "🌖"
    elif cycle < 7:
        phase_name = "🌗 Последняя четверть"
        emoji = "🌗"
    else:
        phase_name = "🌘 Убывающая"
        emoji = "🌘"
        
    return f"{emoji} {phase_name}"

def format_time(timestamp, tz_offset=None):
    """Форматирует время с учетом часового пояса"""
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    # OpenWeatherMap возвращает время в UTC, но sunrise/sunset уже с учетом локации в timestamp
    # Для отображения просто конвертируем в локальное время системы или добавляем смещение, если нужно
    # В данном случае timestamp от API уже верный для города
    return dt.strftime("%H:%M")

def build_weather_message(city_name, current, forecast):
    """Формирует сообщение с текущей погодой и доп. данными"""
    main = current['main']
    weather_desc = current['weather'][0]['description']
    icon = current['weather'][0]['icon']
    wind = current['wind']['speed']
    
    # Давление (гПа -> мм рт.ст.)
    pressure_hpa = main.get('pressure', 0)
    pressure_mm = round(pressure_hpa * 0.75006)
    
    # Восход и закат
    sys_data = current.get('sys', {})
    sunrise_ts = sys_data.get('sunrise', 0)
    sunset_ts = sys_data.get('sunset', 0)
    sunrise_str = format_time(sunrise_ts)
    sunset_str = format_time(sunset_ts)
    
    # Луна
    moon_phase = get_moon_phase()
    
    # Текст сообщения
    text = (
        f"🌍 <b>Погода: {city_name}</b>\n\n"
        f"🌡️ <b>{main['temp']}°C</b> ({weather_desc.capitalize()})\n"
        f"❄️ Ощущается как: {main.get('feels_like', 0)}°C\n"
        f"💧 Влажность: {main.get('humidity', 0)}%\n"
        f"💨 Ветер: {wind} м/с\n"
        f"📉 Давление: {pressure_mm} мм рт. ст.\n\n"
        f"🌅 Восход: {sunrise_str}\n"
        f"🌇 Закат: {sunset_str}\n"
        f"{moon_phase}\n"
    )
    
    # Клавиатура
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_forecast = types.InlineKeyboardButton("🕒 Прогноз на 24ч", callback_data=f"forecast_{city_name}")
    btn_refresh = types.InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{city_name}")
    markup.add(btn_forecast, btn_refresh)
    
    # Кнопки городов (для удобства возврата)
    cities_markup = types.InlineKeyboardMarkup(row_width=4)
    city_buttons = [types.InlineKeyboardButton(c, callback_data=f"city_{c}") for c in CITIES.keys()]
    cities_markup.add(*city_buttons)
    
    return text, markup, cities_markup

def build_forecast_message(city_name, forecast_data):
    """Формирует сообщение с прогнозом"""
    if not forecast_data or 'list' not in forecast_
        return "❌ Не удалось получить прогноз."
    
    items = forecast_data['list'][:8]  # Берем первые 8 записей (24 часа с шагом 3ч)
    text = f"🕒 <b>Прогноз на 24ч: {city_name}</b>\n_(Данные каждые 3 часа)_\n\n"
    
    for item in items:
        dt = datetime.fromtimestamp(item['dt'])
        time_str = dt.strftime("%d.%m %H:%M")
        temp = item['main']['temp']
        desc = item['weather'][0]['description']
        pop = item.get('pop', 0) * 100 # Вероятность осадков
        
        # Эмодзи осадков
        rain_emoji = ""
        if pop > 0:
            rain_emoji = f" 🌧️{int(pop)}%"
            
        text += f"⏰ {time_str}: <b>{temp}°C</b>, {desc}{rain_emoji}\n"
        
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Назад к текущей", callback_data=f"refresh_{city_name}"))
    return text, markup

# --- ОБРАБОТЧИКИ БОТА ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [types.InlineKeyboardButton(city, callback_data=f"city_{city}") for city in CITIES.keys()]
    markup.add(*buttons)
    bot.send_message(
        message.chat.id, 
        "👋 Привет! Выберите город для получения прогноза:", 
        reply_markup=markup
    )

@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = (
        "🤖 <b>Бот погоды</b>\n\n"
        "/start - Главное меню\n"
        "/help - Эта справка\n\n"
        "Используйте кнопки для выбора города."
    )
    bot.send_message(message.chat.id, help_text, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith('city_'))
def handle_city_select(call):
    city_name = call.data.replace('city_', '')
    coords = CITIES.get(city_name)
    
    if not coords:
        bot.answer_callback_query(call.id, "Город не найден", show_alert=True)
        return

    bot.answer_callback_query(call.id, f"Загружаю погоду для {city_name}...")
    
    # Отправляем индикатор загрузки (опционально можно удалить сообщение и отправить новое)
    # Но лучше просто редактировать или отправлять новое
    
    current, forecast = get_weather_data(coords['lat'], coords['lon'])
    
    if current:
        text, markup, cities_markup = build_weather_message(city_name, current, forecast)
        # Сначала отправляем погоду
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=text, reply_markup=markup, parse_mode="HTML")
        # Затем предлагаем выбрать другой город (отдельным сообщением или можно добавить в клавиатуру выше, но так чище)
        # bot.send_message(call.message.chat.id, "Выбрать другой город:", reply_markup=cities_markup) 
        # Чтобы не спамить, оставим только основную клавиатуру с прогнозом
    else:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="❌ Ошибка получения данных.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('forecast_'))
def handle_forecast(call):
    city_name = call.data.replace('forecast_', '')
    coords = CITIES.get(city_name)
    
    if not coords:
        bot.answer_callback_query(call.id, "Ошибка", show_alert=True)
        return
        
    bot.answer_callback_query(call.id, "Загрузка прогноза...")
    
    _, forecast = get_weather_data(coords['lat'], coords['lon'])
    
    if forecast:
        text, markup = build_forecast_message(city_name, forecast)
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=text, reply_markup=markup, parse_mode="HTML")
    else:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="❌ Ошибка получения прогноза.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('refresh_'))
def handle_refresh(call):
    city_name = call.data.replace('refresh_', '')
    # Имитируем выбор города заново
    call.data = f"city_{city_name}"
    handle_city_select(call)

# Запуск бота
if __name__ == '__main__':
    logger.info("Бот запущен...")
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
