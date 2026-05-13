import os
import time
import math
import threading
import requests
import telebot
from telebot import types
from datetime import datetime, timezone, timedelta

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

if not BOT_TOKEN or not WEATHER_API_KEY:
    print("ОШИБКА: Не найдены переменные окружения TELEGRAM_BOT_TOKEN или WEATHER_API_KEY")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# Хранилище последнего выбранного города для каждого пользователя
# Структура: { chat_id: "НазваниеГорода" }
user_last_city = {}

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

def get_moon_phase():
    known_new_moon = datetime(2001, 1, 1, 12, 24, 0, tzinfo=timezone.utc)
    synodic_month = 29.53058867
    now = datetime.now(timezone.utc)
    diff_days = (now - known_new_moon).total_seconds() / 86400
    cycles = diff_days / synodic_month
    current_cycle_pos = cycles - int(cycles)
    age = current_cycle_pos * synodic_month
    
    if age < 1: return "🌑 Новолуние"
    elif age < 7: return "🌒 Растущая"
    elif age < 8: return "🌓 Первая четверть"
    elif age < 14: return "🌔 Растущая"
    elif age < 15: return "🌕 Полнолуние"
    elif age < 21: return "🌖 Убывающая"
    elif age < 22: return "🌗 Последняя четверть"
    else: return "🌘 Убывающая"

def format_time(timestamp, tz_offset):
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    offset_hours = int(tz_offset / 3600)
    local_dt = dt + timedelta(hours=offset_hours)
    return local_dt.strftime("%H:%M")

def get_weather_data(city_name):
    """Возвращает текст прогноза и данные для отправки"""
    coords = CITIES[city_name]
    lat = coords['lat']
    lon = coords['lon']
    
    url_current = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    
    try:
        resp = requests.get(url_current, timeout=10)
        if resp.status_code != 200:
            return None
            
        data = resp.json()
        
        temp = data['main']['temp']
        feels_like = data['main']['feels_like']
        pressure_hpa = data['main']['pressure']
        pressure_mm = round(pressure_hpa * 0.75006)
        humidity = data['main']['humidity']
        wind_speed = data['wind']['speed']
        desc = data['weather'][0]['description']
        icon = data['weather'][0]['icon']
        emoji = get_weather_icon_code(icon)
        
        sunrise_ts = data['sys']['sunrise']
        sunset_ts = data['sys']['sunset']
        timezone_offset = data['timezone']
        
        sunrise_str = format_time(sunrise_ts, timezone_offset)
        sunset_str = format_time(sunset_ts, timezone_offset)
        moon_phase = get_moon_phase()
        
        text = (
            f"☀️ <b>Доброе утро! Прогноз для {city_name}</b>\n\n"
            f"{emoji} <b>{desc.capitalize()}</b>\n"
            f"🌡️ Температура: <b>{temp}°C</b> (ощущается как {feels_like}°C)\n"
            f"💨 Ветер: {wind_speed} м/с\n"
            f"💧 Влажность: {humidity}%\n"
            f"📉 Давление: <b>{pressure_mm} мм рт. ст.</b>\n\n"
            f"🌅 Восход: {sunrise_str}\n"
            f"🌇 Закат: {sunset_str}\n"
            f"🌙 Луна: {moon_phase}\n\n"
            f"<i>Хорошего дня!</i>"
        )
        return text
    except Exception as e:
        print(f"Error fetching weather: {e}")
        return None

# --- ПЛАНИРОВЩИК (ФОНОВЫЙ ПОТОК) ---

def morning_scheduler():
    """Проверяет каждую минуту, не наступило ли 7:30"""
    last_notification_minute = -1
    
    while True:
        try:
            now = datetime.now()
            current_hour = now.hour
            current_minute = now.minute
            
            # Проверяем время 07:30
            # Чтобы не спамить каждую минуту в 7:30, запоминаем последнюю минуту отправки
            if current_hour == 7 and current_minute == 30 and current_minute != last_notification_minute:
                last_notification_minute = current_minute
                
                print(f"Время 07:30! Отправка уведомлений для {len(user_last_city)} пользователей.")
                
                for chat_id, city in user_last_city.items():
                    if city in CITIES:
                        weather_text = get_weather_data(city)
                        if weather_text:
                            try:
                                bot.send_message(chat_id, weather_text, parse_mode='HTML')
                                print(f"Отправлено пользователю {chat_id} ({city})")
                            except Exception as e:
                                print(f"Ошибка отправки пользователю {chat_id}: {e}")
                                # Если бот заблокирован, можно удалить из списка (опционально)
                                # user_last_city.pop(chat_id, None)
            
            # Сброс счетчика, если минута прошла (на случай если скрипт работал в 7:30 и перешел в 7:31)
            if current_minute != 30:
                last_notification_minute = -1
                
            time.sleep(60) # Ждем 1 минуту перед следующей проверкой
            
        except Exception as e:
            print(f"Scheduler error: {e}")
            time.sleep(60)

# --- ОБРАБОТЧИКИ СООБЩЕНИЙ ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for city in CITIES.keys():
        markup.add(city)
    
    welcome_text = (
        "👋 Привет! Я бот прогноза погоды.\n\n"
        "Выберите город из меню ниже или используйте команду:\n"
        "/weather <город>\n\n"
        "🔔 <b>Новое:</b> Теперь я буду присылать вам прогноз каждое утро в 07:30 автоматически для последнего выбранного города!"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in CITIES)
def handle_city_selection(message):
    city_name = message.text
    # Сохраняем выбор пользователя
    user_last_city[message.chat.id] = city_name
    send_weather(message.chat.id, city_name)

@bot.message_handler(commands=['weather'])
def handle_weather_command(message):
    try:
        city_name = message.text.split(maxsplit=1)[1].strip().capitalize()
        found_city = None
        for key in CITIES.keys():
            if key.lower() == city_name.lower():
                found_city = key
                break
        
        if found_city:
            user_last_city[message.chat.id] = found_city
            send_weather(message.chat.id, found_city)
        else:
            bot.reply_to(message, f"Город '{city_name}' не найден. Выберите из меню.")
    except IndexError:
        bot.reply_to(message, "Пожалуйста, укажите город. Пример: /weather Москва")

def send_weather(chat_id, city_name):
    coords = CITIES[city_name]
    lat = coords['lat']
    lon = coords['lon']
    
    url_current = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    url_forecast = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    
    try:
        resp_curr = requests.get(url_current, timeout=10)
        resp_fore = requests.get(url_forecast, timeout=10)
        
        if resp_curr.status_code != 200:
            bot.send_message(chat_id, "Ошибка получения данных.")
            return
            
        data_curr = resp_curr.json()
        data_fore = resp_fore.json()
        
        temp = data_curr['main']['temp']
        feels_like = data_curr['main']['feels_like']
        pressure_hpa = data_curr['main']['pressure']
        pressure_mm = round(pressure_hpa * 0.75006)
        humidity = data_curr['main']['humidity']
        wind_speed = data_curr['wind']['speed']
        desc = data_curr['weather'][0]['description']
        icon = data_curr['weather'][0]['icon']
        emoji = get_weather_icon_code(icon)
        
        sunrise_ts = data_curr['sys']['sunrise']
        sunset_ts = data_curr['sys']['sunset']
        timezone_offset = data_curr['timezone']
        
        sunrise_str = format_time(sunrise_ts, timezone_offset)
        sunset_str = format_time(sunset_ts, timezone_offset)
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
        
        markup = types.InlineKeyboardMarkup()
        btn_forecast = types.InlineKeyboardButton("🕒 Прогноз на 24ч", callback_data=f"forecast_{city_name}")
        btn_refresh = types.InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{city_name}")
        markup.add(btn_forecast, btn_refresh)
        
        bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=markup)
        
    except Exception as e:
        print(f"Error: {e}")
        bot.send_message(chat_id, "Произошла ошибка.")

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
        
        for item in forecast_list[:8]:
            dt_txt = item['dt_txt']
            time_str = dt_txt.split()[1][:5] 
            temp = item['main']['temp']
            desc = item['weather'][0]['description']
            pop = item.get('pop', 0) * 100
            
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
    user_last_city[call.message.chat.id] = city_name # Обновляем последний город при ручном обновлении
    bot.delete_message(call.message.chat.id, call.message.message_id)
    send_weather(call.message.chat.id, city_name)

# --- ЗАПУСК ---

if __name__ == '__main__':
    print("Запуск планировщика утренних уведомлений...")
    # Запускаем планировщик в отдельном потоке, чтобы он не блокировал работу бота
    scheduler_thread = threading.Thread(target=morning_scheduler, daemon=True)
    scheduler_thread.start()
    
    print("Запуск бота...")
    bot.infinity_polling()
