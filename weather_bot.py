import os
import sys
import json
import requests
from datetime import datetime, timezone, timedelta
from math import radians, sin, cos, sqrt, atan2
import telebot

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
# WEATHER_API_KEY больше не нужен для Open-Meteo!
USERS_FILE = 'users.json'

if not BOT_TOKEN:
    print("❌ ОШИБКА: Не найдена переменная окружения TELEGRAM_BOT_TOKEN")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

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

def get_weather_emoji(code, is_day=1):
    """Конвертирует код погоды WMO в эмодзи"""
    # Коды WMO: https://open-meteo.com/en/docs
    if code == 0: return "☀️" if is_day else "🌙" # Ясно
    if 1 <= code <= 3: return "⛅" if is_day else "☁️" # Преимущественно ясно / облачно
    if 45 <= code <= 48: return "🌫️" # Туман
    if 51 <= code <= 55: return "🌦️" # Морось
    if 61 <= code <= 67: return "🌧️" # Дождь
    if 71 <= code <= 77: return "❄️" # Снег
    if 80 <= code <= 82: return "🌦️" # Ливень
    if 85 <= code <= 86: return "🌨️" # Снегопад
    if 95 <= code <= 99: return "⛈️" # Гроза
    return "🌡️"

def get_weather_description(code):
    """Текстовое описание по коду WMO"""
    descriptions = {
        0: "Ясно", 1: "Преимущественно ясно", 2: "Переменная облачность", 3: "Пасмурно",
        45: "Туман", 48: "Иней",
        51: "Легкая морось", 53: "Морось", 55: "Плотная морось",
        61: "Слабый дождь", 63: "Дождь", 65: "Сильный дождь",
        71: "Слабый снег", 73: "Снег", 75: "Сильный снег",
        80: "Слабый ливень", 81: "Ливень", 82: "Сильный ливень",
        95: "Гроза", 96: "Гроза с градом", 99: "Сильная гроза с градом"
    }
    return descriptions.get(code, "Неизвестно")

def get_moon_phase():
    """Расчет фазы луны"""
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

# --- ОСНОВНАЯ ЛОГИКА ПОГОДЫ (OPEN-METEO) ---

def get_city_weather_data(city_name, forecast_hours=24):
    if city_name not in CITIES:
        return None
    
    coords = CITIES[city_name]
    lat = coords['lat']
    lon = coords['lon']
    
    # Формируем URL для Open-Meteo
    # Параметры: текущая погода + почасовой прогноз
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,"
        f"surface_pressure,wind_speed_10m,visibility,cloud_cover"
        f"&hourly=temperature_2m,weather_code,precipitation_probability,precipitation"
        f"&timezone=auto" # Автоматическое определение часового пояса
    )
    
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            print(f"API Error: {resp.status_code}")
            return None
        
        data = resp.json()
        
        # --- Обработка текущих данных ---
        curr = data.get('current', {})
        current_temp = curr.get('temperature_2m')
        feels_like = curr.get('apparent_temperature')
        humidity = curr.get('relative_humidity_2m')
        pressure_hpa = curr.get('surface_pressure')
        pressure_mm = round(pressure_hpa * 0.75006) if pressure_hpa else 0
        wind_speed = curr.get('wind_speed_10m')
        visibility_m = curr.get('visibility') # в метрах
        visibility_km = round(visibility_m / 1000) if visibility_m else "N/A"
        cloud_cover = curr.get('cloud_cover')
        
        weather_code = curr.get('weather_code', 0)
        desc = get_weather_description(weather_code)
        emoji = get_weather_emoji(weather_code)
        
        # Часовой пояс (смещение в часах от UTC)
        tz_offset_str = data.get('timezone_abbreviation', 'UTC')
        
        # --- Обработка прогноза (почасовой) ---
        hourly = data.get('hourly', {})
        time_list = hourly.get('time', [])
        temp_list = hourly.get('temperature_2m', [])
        code_list = hourly.get('weather_code', [])
        precip_prob_list = hourly.get('precipitation_probability', [])
        precip_amt_list = hourly.get('precipitation', []) # мм/час
        
        # Берем следующие 24 часа (или сколько есть)
        # Время приходит в формате ISO: "2023-10-25T14:00"
        forecast_data = []
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
        
        # Находим индекс текущего часа
        start_index = 0
        for i, t in enumerate(time_list):
            if t.startswith(now_iso[:13]): # Сравнение по YYYY-MM-DDTHH
                start_index = i
                break
        
        # Собираем данные на 24 часа вперед
        count = 0
        for i in range(start_index, len(time_list)):
            if count >= 24: break
            
            t_str = time_list[i].split('T')[1] # "14:00" -> "14:00" (берем время)
            # Округляем до минут для красоты, если нужно, но там обычно :00
            hour_display = t_str[:5] 
            
            forecast_data.append({
                "time": hour_display,
                "temp": temp_list[i],
                "code": code_list[i],
                "prob": precip_prob_list[i],
                "amount": precip_amt_list[i]
            })
            count += 1
            
        return {
            "city": city_name,
            "coords": f"{lat}, {lon}",
            "tz": tz_offset_str,
            "temp": current_temp,
            "feels_like": feels_like,
            "desc": desc,
            "emoji": emoji,
            "humidity": humidity,
            "pressure_mm": pressure_mm,
            "wind": wind_speed,
            "visibility_km": visibility_km,
            "clouds": cloud_cover,
            "forecast": forecast_data
        }
        
    except Exception as e:
        print(f"Error fetching Open-Meteo: {e}")
        return None

def format_forecast_message(data):
    """Формирует текст прогноза на 24 часа"""
    lines = [f"🕒 <b>Прогноз по часам ({data['city']})</b>\n"]
    
    for item in data['forecast']:
        emoji = get_weather_emoji(item['code'])
        temp = item['temp']
        prob = item['prob']
        amount = item['amount']
        
        line = f"⏰ <b>{item['time']}</b>: {temp}°C {emoji}"
        
        # Добавляем информацию об осадках, если вероятность > 0
        if prob > 0:
            if amount > 0:
                line += f"\n   💧 {prob}% ({amount} мм)"
            else:
                line += f"\n   💧 Вероятность: {prob}%"
        
        lines.append(line)
        lines.append("") # Пустая строка для разделения
        
    return "\n".join(lines)

def format_current_message(data):
    """Формирует основное сообщение с текущей погодой"""
    text = (
        f"📍 <b>{data['city']}</b> ({data['coords']})\n"
        f"🕒 Часовой пояс: {data['tz']}\n\n"
        f"{data['emoji']} <b>{data['desc']}</b>\n\n"
        f"🌡️ Температура: <b>{data['temp']}°C</b> (ощущается как {data['feels_like']}°C)\n"
        f"💨 Ветер: {data['wind']} м/с\n"
        f"💧 Влажность: {data['humidity']}%\n"
        f"☁️ Облачность: {data['clouds']}%\n"
        f"👁️ Видимость: {data['visibility_km']} км\n"
        f"📉 Давление: <b>{data['pressure_mm']} мм рт. ст.</b>\n\n"
        f"🌙 Луна: {get_moon_phase()}"
    )
    return text

# --- РАБОТА С БАЗОЙ ПОЛЬЗОВАТЕЛЕЙ ---

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading users: {e}")
        return {}

def save_user(user_id, city):
    users = load_users()
    users[str(user_id)] = city
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving user: {e}")

# --- ОБРАБОТЧИКИ БОТА ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    for city in CITIES.keys():
        markup.add(city)
    bot.send_message(message.chat.id,
        "👋 Привет! Я бот погоды на базе <b>Open-Meteo</b>.\n\n"
        "Выберите город, чтобы получить точный прогноз:\n"
        "- Почасовые данные\n"
        "- Количество осадков в мм\n"
        "- Видимость и облачность\n\n"
        "Я сохраню город для утренней рассылки в 7:30.",
        reply_markup=markup, parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text in CITIES)
def handle_city(message):
    city = message.text
    save_user(message.chat.id, city)
    
    bot.send_chat_action(message.chat.id, 'typing')
    data = get_city_weather_data(city)
    
    if data:
        text = format_current_message(data)
        markup = telebot.types.InlineKeyboardMarkup()
        btn_forecast = telebot.types.InlineKeyboardButton("🕒 Прогноз на 24ч", callback_data=f"forecast_{city}")
        btn_refresh = telebot.types.InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{city}")
        markup.add(btn_forecast, btn_refresh)
        
        bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)
        bot.send_message(message.chat.id, "✅ Город сохранен для утренней рассылки!")
    else:
        bot.send_message(message.chat.id, "❌ Ошибка получения данных. Попробуйте позже.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('forecast_'))
def handle_forecast_callback(call):
    city = call.data.split('_')[1]
    bot.answer_callback_query(call.id)
    
    data = get_city_weather_data(city)
    if data:
        text = format_forecast_message(data)
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=text, parse_mode='HTML')
    else:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Ошибка загрузки прогноза.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('refresh_'))
def handle_refresh_callback(call):
    city = call.data.split('_')[1]
    bot.delete_message(call.message.chat.id, call.message.message_id)
    handle_city(type('obj', (object,), {'text': city, 'chat': type('obj', (object,), {'id': call.message.chat.id})})())

# --- РЕЖИМ РАССЫЛКИ ---

def run_morning_broadcast():
    print("🚀 Запуск утренней рассылки (Open-Meteo)...")
    users = load_users()
    if not users:
        print("⚠️ Нет пользователей.")
        return

    success_count = 0
    for user_id_str, city in users.items():
        user_id = int(user_id_str)
        data = get_city_weather_data(city)
        
        if data:
            # Для утра добавим приветствие
            header = f"☀️ <b>Доброе утро!</b>\nПогода в {city}:\n\n"
            text = header + format_current_message(data)
            
            try:
                bot.send_message(user_id, text, parse_mode='HTML')
                success_count += 1
                print(f"✅ Отправлено пользователю {user_id}")
            except Exception as e:
                print(f"❌ Ошибка отправки {user_id}: {e}")
        else:
            print(f"⚠️ Нет данных для {city}")

    print(f"🏁 Готово: {success_count}/{len(users)}")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--send-morning':
        run_morning_broadcast()
    else:
        print("🤖 Запуск бота...")
        try:
            bot.infinity_polling()
        except Exception as e:
            print(f"Critical error: {e}")
