import os
import time
import math
import requests
import telebot
from telebot import types
from datetime import datetime, timezone

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

if not BOT_TOKEN or not WEATHER_API_KEY:
    print("ОШИБКА: Не найдены переменные окружения TELEGRAM_BOT_TOKEN или WEATHER_API_KEY")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# Список городов с координатами
CITIES = {
    "Москва": {"lat": 55.75, "lon": 37.61},
    "Санкт-Петербург": {"lat": 59.93, "lon": 30.33},
    "Казань": {"lat": 55.79, "lon": 49.11},
    "Новосибирск": {"lat": 55.00, "lon": 82.93},
    "Екатеринбург": {"lat": 56.84, "lon": 60.61},
    "Нижний Новгород": {"lat": 56.32, "lon": 44.00},
    "Сочи": {"lat": 43.60, "lon": 39.73},
    "Владивосток": {"lat": 43.11, "lon": 131.88}
}

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_weather_icon_code(icon_name):
    """Возвращает эмодзи по коду иконки OpenWeatherMap"""
    icons = {
        "01d": "☀️", "01n": "🌙",
        "02d": "⛅", "02n": "☁️",
        "03d": "☁️", "03n": "☁️",
        "04d": "☁️", "04n": "☁️",
        "09d": "🌧️", "09n": "🌧️",
        "10d": "🌦️", "10n": "🌧️",
        "11d": "⛈️", "11n": "⛈️",
        "13d": "❄️", "13n": "❄️",
        "50d": "🌫️", "50n": "🌫️"
    }
    return icons.get(icon_name, "🌡️")

def get_moon_phase(day_offset=0):
    """Рассчитывает фазу луны. day_offset - смещение дней от сегодня."""
    # Базовая дата новолуния (известное новолуние)
    known_new_moon = datetime(2001, 1, 1, 12, 24, 0, tzinfo=timezone.utc)
    synodic_month = 29.53058867
    
    now = datetime.now(timezone.utc)
    # Добавляем смещение для прогноза (если нужно, но для текущей погоды 0)
    target_date = now
    
    diff_days = (target_date - known_new_moon).total_seconds() / 86400
    cycles = diff_days / synodic_month
    current_cycle_pos = cycles - int(cycles)
    age = current_cycle_pos * synodic_month
    
    if age < 1: phase = "🌑 Новолуние"
    elif age < 7: phase = "🌒 Растущая"
    elif age < 8: phase = "🌓 Первая четверть"
    elif age < 14: phase = "🌔 Растущая"
    elif age < 15: phase = "🌕 Полнолуние"
    elif age < 21: phase = "🌖 Убывающая"
    elif age < 22: phase = "🌗 Последняя четверть"
    else: phase = "🌘 Убывающая"
    
    return phase

def format_time(timestamp, tz_offset):
    """Конвертирует Unix timestamp в время с учетом часового пояса города"""
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    # Смещение в часах
    offset_hours = int(tz_offset / 3600)
    # Простая коррекция времени (для точности лучше использовать pytz, но здесь упрощено)
    from datetime import timedelta
    local_dt = dt + timedelta(hours=offset_hours)
    return local_dt.strftime("%H:%M")

# --- ОСНОВНАЯ ЛОГИКА ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for city in CITIES.keys():
        markup.add(city)
    
    welcome_text = (
        "👋 Привет! Я бот прогноза погоды.\n\n"
        "Выберите город из меню ниже или используйте команду:\n"
        "/weather <город> (например: /weather Москва)\n\n"
        "Я покажу температуру, давление, ветер, восход/закат и фазу луны!"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in CITIES)
def handle_city_selection(message):
    city_name = message.text
    send_weather(message.chat.id, city_name)

@bot.message_handler(commands=['weather'])
def handle_weather_command(message):
    try:
        # Получаем аргумент команды: /weather Москва -> Москва
        city_name = message.text.split(maxsplit=1)[1]
        # Нормализация названия (первая буква заглавная)
        city_name = city_name.strip().capitalize()
        
        # Проверка, есть ли город в списке (нужно точное совпадение ключей)
        # Для гибкости попробуем найти похожее название
        found_city = None
        for key in CITIES.keys():
            if key.lower() == city_name.lower():
                found_city = key
                break
        
        if found_city:
            send_weather(message.chat.id, found_city)
        else:
            bot.reply_to(message, f"Город '{city_name}' не найден в моем списке. Выберите из меню.")
    except IndexError:
        bot.reply_to(message, "Пожалуйста, укажите город. Пример: /weather Москва")

def send_weather(chat_id, city_name):
    coords = CITIES[city_name]
    lat = coords['lat']
    lon = coords['lon']
    
    # Запрос текущей погоды и прогноза (onecall API требует подписки, используем стандартные endpoints)
    # 1. Текущая погода
    url_current = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    # 2. Прогноз
    url_forecast = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    
    try:
        resp_curr = requests.get(url_current, timeout=10)
        resp_fore = requests.get(url_forecast, timeout=10)
        
        if resp_curr.status_code != 200:
            bot.send_message(chat_id, "Ошибка получения данных о погоде. Попробуйте позже.")
            return
            
        data_curr = resp_curr.json()
        data_fore = resp_fore.json()
        
        # --- Формирование сообщения о текущей погоде ---
        temp = data_curr['main']['temp']
        feels_like = data_curr['main']['feels_like']
        pressure_hpa = data_curr['main']['pressure']
        pressure_mm = round(pressure_hpa * 0.75006) # Конвертация в мм рт.ст.
        humidity = data_curr['main']['humidity']
        wind_speed = data_curr['wind']['speed']
        desc = data_curr['weather'][0]['description']
        icon = data_curr['weather'][0]['icon']
        emoji = get_weather_icon_code(icon)
        
        # Восход и закат
        sunrise_ts = data_curr['sys']['sunrise']
        sunset_ts = data_curr['sys']['sunset']
        timezone_offset = data_curr['timezone']
        
        sunrise_str = format_time(sunrise_ts, timezone_offset)
        sunset_str = format_time(sunset_ts, timezone_offset)
        
        # Луна
        moon_phase = get_moon_phase()
        
        text = (
            f"📍 <b>{city_name}</b>\n"
            f"{emoji} <b>{desc.capitalize()}</b>\n\n"
            f"🌡️ Температура: <b>{temp}°C</b> (ощущается как {feels_like}°C)\n"
            f"💨 Ветер: {wind_speed} м/с\n"
            f"💧 Влажность: {humidity}%\n"
            f"📉 Давление: <b>{pressure_mm} мм рт. ст.</b>\n\n"
            f"🌅 Восход: {sunrise_str}\n"
            f"🌇 Закат: {sunset_str}\n"
            f"🌙 Луна: {moon_phase}"
        )
        
        # Кнопки управления
        markup = types.InlineKeyboardMarkup()
        btn_forecast = types.InlineKeyboardButton("🕒 Прогноз на 24ч", callback_data=f"forecast_{city_name}")
        btn_refresh = types.InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{city_name}")
        markup.add(btn_forecast, btn_refresh)
        
        bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=markup)
        
    except Exception as e:
        print(f"Error: {e}")
        bot.send_message(chat_id, "Произошла ошибка при обработке запроса.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('forecast_'))
def handle_forecast_callback(call):
    city_name = call.data.split('_')[1]
    coords = CITIES[city_name]
    
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={coords['lat']}&lon={coords['lon']}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            bot.answer_callback_query(call.id, "Ошибка загрузки прогноза", show_alert=True)
            return
            
        data = resp.json()
        forecast_list = data.get('list', [])
        
        if not forecast_list:
            bot.answer_callback_query(call.id, "Нет данных прогноза", show_alert=True)
            return
        
        msg_text = f"🕒 <b>Прогноз на 24 часа ({city_name})</b>\n<i>(Данные каждые 3 часа)</i>\n\n"
        
        # Берем первые 8 записей (24 часа / 3 часа = 8 записей)
        for item in forecast_list[:8]:
            dt_txt = item['dt_txt'] # Дата в формате YYYY-MM-DD HH:MM:SS
            # Вырезаем время (последние 5 символов)
            time_str = dt_txt.split()[1][:5] 
            temp = item['main']['temp']
            desc = item['weather'][0]['description']
            pop = item.get('pop', 0) * 100 # Вероятность осадков
            
            icon = item['weather'][0]['icon']
            emoji = get_weather_icon_code(icon)
            
            msg_text += f"⏰ <b>{time_str}</b>: {temp}°C {emoji}\n"
            msg_text += f"   {desc.capitalize()}, осадки: {int(pop)}%\n\n"
            
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=msg_text, parse_mode='HTML')
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        print(f"Forecast Error: {e}")
        bot.answer_callback_query(call.id, "Ошибка", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('refresh_'))
def handle_refresh_callback(call):
    city_name = call.data.split('_')[1]
    bot.delete_message(call.message.chat.id, call.message.message_id)
    send_weather(call.message.chat.id, city_name)

# Запуск бота
if __name__ == '__main__':
    print("Бот запущен...")
    bot.infinity_polling()
