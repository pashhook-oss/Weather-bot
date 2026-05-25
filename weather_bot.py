import os
import sys
import json
import requests
from datetime import datetime, timezone, timedelta
import telebot
from telebot import types

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
USERS_FILE = 'users.json'

if not BOT_TOKEN:
    print("❌ ОШИБКА: Не найдена переменная окружения TELEGRAM_BOT_TOKEN")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')

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
    codes = {
        0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️",
        45: "🌫️", 48: "🌫️",
        51: "🌦️", 53: "🌧️", 55: "🌧️",
        61: "🌧️", 63: "🌧️", 65: "⛈️",
        71: "❄️", 73: "❄️", 75: "❄️",
        80: "🌦️", 81: "🌧️", 82: "⛈️",
        95: "⛈️", 96: "⛈️", 99: "⛈️"
    }
    return codes.get(code, "🌡️")

def get_weather_desc(code):
    descs = {
        0: "Ясно", 1: "Преимущественно ясно", 2: "Переменная облачность", 3: "Пасмурно",
        45: "Туман", 48: "Иней",
        51: "Морось", 53: "Морось", 55: "Сильная морось",
        61: "Дождь", 63: "Дождь", 65: "Ливень",
        71: "Снег", 73: "Снег", 75: "Снегопад",
        80: "Ливень", 81: "Ливень", 82: "Шквал",
        95: "Гроза", 96: "Гроза с градом", 99: "Сильная гроза"
    }
    return descs.get(code, "Неизвестно")

def get_moon_phase():
    # Упрощенная логика фазы
    now = datetime.now(timezone.utc)
    # Известное новолуние
    ref = datetime(2000, 1, 6, 12, 24, tzinfo=timezone.utc)
    diff = (now - ref).total_seconds() / 86400
    cycle = diff % 29.53
    
    if cycle < 1: return "🌑 Новолуние"
    elif cycle < 7: return "🌒 Растущая"
    elif cycle < 14: return "🌓 Первая четверть"
    elif cycle < 22: return "🌕 Полнолуние"
    else: return "🌗 Убывающая"

# --- ЗАПРОС К OPEN-METEO ---

def fetch_weather(city_name):
    if city_name not in CITIES:
        return None
    
    lat = CITIES[city_name]['lat']
    lon = CITIES[city_name]['lon']
    
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,surface_pressure,wind_speed_10m,visibility,cloud_cover",
        "hourly": "temperature_2m,relative_humidity_2m,surface_pressure,weather_code",
        "timezone": "auto",
        "forecast_days": 7
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status() # Проверка на ошибки HTTP
        data = response.json()
        
        if 'current' not in data or 'hourly' not in data:
            return None
            
        return data
    except Exception as e:
        print(f"Error fetching weather: {e}")
        return None

def format_current_message(city, data):
    curr = data['current']
    code = curr.get('weather_code', 0)
    
    text = (
        f"📍 <b>{city}</b>\n"
        f"{get_weather_emoji(code)} <b>{get_weather_desc(code)}</b>\n\n"
        f"🌡️ <b>{curr['temperature_2m']}°C</b> (ощущается {curr['apparent_temperature']}°C)\n"
        f"💨 Ветер: {curr['wind_speed_10m']} м/с\n"
        f"💧 Влажность: {curr['relative_humidity_2m']}%\n"
        f"👁️ Видимость: {round(curr.get('visibility', 0)/1000)} км\n"
        f"☁️ Облачность: {curr.get('cloud_cover', 0)}%\n"
        f"📉 Давление: {round(curr['surface_pressure'] * 0.75006)} мм рт.ст.\n\n"
        f"🌙 Луна: {get_moon_phase()}"
    )
    return text

def format_weekly_forecast(data):
    hourly = data['hourly']
    times = hourly['time']
    temps = hourly['temperature_2m']
    hums = hourly['relative_humidity_2m']
    press = hourly['surface_pressure']
    codes = hourly['weather_code']
    
    # Группируем по дням и времени суток (Утро: 6-11, День: 12-17, Вечер: 18-23)
    forecast_text = "📅 <b>Прогноз на 7 дней</b>\n\n"
    
    current_date = ""
    
    # Проходим по всем часам (берем с запасом на неделю)
    for i in range(len(times)):
        dt_str = times[i] # "2023-10-25T14:00"
        date_part = dt_str.split('T')[0]
        hour_part = int(dt_str.split('T')[1].split(':')[0])
        
        # Определяем часть дня
        time_label = ""
        if 6 <= hour_part <= 11: time_label = "Утро"
        elif 12 <= hour_part <= 17: time_label = "День"
        elif 18 <= hour_part <= 23: time_label = "Вечер"
        else: continue # Ночь пропускаем для краткости
        
        # Если новый день, добавляем заголовок
        if date_part != current_date:
            # Форматируем дату красиво (YYYY-MM-DD -> DD.MM)
            d_obj = datetime.strptime(date_part, "%Y-%m-%d")
            date_str = d_obj.strftime("%d.%m (%a)")
            forecast_text += f"<b>{date_str}</b>\n"
            current_date = date_part
        
        # Формируем строку: Утро: 15° ☁️ 65% 750мм
        t = temps[i]
        h = hums[i]
        p = round(press[i] * 0.75006)
        emoji = get_weather_emoji(codes[i])
        
        # Выравнивание пробелами для читаемости
        line = f"{time_label}: {t}° {emoji} | 💧{h}% | 📉{p}\n"
        forecast_text += line
        
        # Если вечер последнего дня или конец цикла, добавляем отступ
        if time_label == "Вечер":
            forecast_text += "\n"
            
    return forecast_text

# --- ЛОГИКА БОТА ---

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    btns = [types.KeyboardButton(city) for city in CITIES.keys()]
    # Добавляем кнопки по 2 в ряд (опционально, можно по одной)
    markup.add(*btns) 
    
    text = (
        "👋 Привет! Выберите город для прогноза:\n"
        "Я покажу погоду сейчас и прогноз на неделю."
    )
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in CITIES)
def handle_city(message):
    city = message.text
    save_user(message.chat.id, city)
    
    bot.send_chat_action(message.chat.id, 'typing')
    data = fetch_weather(city)
    
    if not data:
        bot.reply_to(message, "❌ Ошибка получения данных. Попробуйте позже.")
        return
    
    # Текущая погода
    curr_text = format_current_message(city, data)
    
    # Кнопки
    markup = types.InlineKeyboardMarkup()
    btn_week = types.InlineKeyboardButton("📅 Прогноз на неделю", callback_data=f"week_{city}")
    btn_ref = types.InlineKeyboardButton("🔄 Обновить", callback_data=f"ref_{city}")
    markup.add(btn_week, btn_ref)
    
    bot.send_message(message.chat.id, curr_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('week_'))
def handle_week_callback(call):
    city = call.data.split('_')[1]
    bot.answer_callback_query(call.id)
    
    data = fetch_weather(city)
    if not data:
        bot.edit_message_text("Ошибка загрузки прогноза.", call.message.chat.id, call.message.message_id)
        return
    
    week_text = format_weekly_forecast(data)
    
    # Telegram имеет лимит на длину сообщения (4096 символов). 
    # Если прогноз слишком длинный, разбиваем его.
    if len(week_text) > 4000:
        # Простое разбиение (можно улучшить)
        parts = [week_text[i:i+4000] for i in range(0, len(week_text), 4000)]
        bot.edit_message_text(parts[0], call.message.chat.id, call.message.message_id)
        for part in parts[1:]:
            bot.send_message(call.message.chat.id, part)
    else:
        bot.edit_message_text(week_text, call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ref_'))
def handle_refresh(call):
    city = call.data.split('_')[1]
    bot.delete_message(call.message.chat.id, call.message.message_id)
    # Эмуляция сообщения выбора города
    msg = type('obj', (object,), {'chat': type('obj', (object,), {'id': call.message.chat.id}), 'text': city})
    handle_city(msg)

# --- БАЗА ПОЛЬЗОВАТЕЛЕЙ ---

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_user(user_id, city):
    users = load_users()
    users[str(user_id)] = city
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

# --- РАССЫЛКА ---

def run_morning_broadcast():
    print("Запуск рассылки...")
    users = load_users()
    count = 0
    for uid, city in users.items():
        data = fetch_weather(city)
        if data:
            txt = f"☀️ <b>Доброе утро!</b>\n{format_current_message(city, data)}"
            try:
                bot.send_message(int(uid), txt)
                count += 1
            except: pass
    print(f"Отправлено: {count}")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--send-morning':
        run_morning_broadcast()
    else:
        print("Бот запущен...")
        bot.infinity_polling()
