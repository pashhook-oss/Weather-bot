import os
import sys
import json
import requests
import threading
from datetime import datetime, timezone, timedelta
from math import radians, sin, cos, sqrt, atan2
import telebot
from flask import Flask, request, jsonify

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
USERS_FILE = 'users.json'
PORT = int(os.environ.get('PORT', 5000)) # Render назначает порт динамически

if not BOT_TOKEN:
    print("❌ ОШИБКА: Не найдена переменная окружения TELEGRAM_BOT_TOKEN")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN, threaded=False) # threaded=False для работы с Flask в одном потоке

# Инициализация Flask для пинга
app = Flask(__name__)

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
    if code == 0: return "☀️" if is_day else "🌙"
    if 1 <= code <= 3: return "⛅" if is_day else "☁️"
    if 45 <= code <= 48: return "🌫️"
    if 51 <= code <= 55: return "🌦️"
    if 61 <= code <= 67: return "🌧️"
    if 71 <= code <= 77: return "❄️"
    if 80 <= code <= 82: return "🌦️"
    if 85 <= code <= 86: return "🌨️"
    if 95 <= code <= 99: return "⛈️"
    return "🌡️"

def get_weather_description(code):
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

# --- ПОГОДА (OPEN-METEO) ---

def get_city_weather_data(city_name):
    if city_name not in CITIES:
        return None
    
    coords = CITIES[city_name]
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={coords['lat']}&longitude={coords['lon']}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,"
        f"surface_pressure,wind_speed_10m,visibility,cloud_cover"
        f"&hourly=temperature_2m,relative_humidity_2m,surface_pressure,weather_code"
        f"&timezone=auto"
    )
    
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        
        data = resp.json()
        curr = data.get('current', {})
        
        # Текущие данные
        result = {
            "city": city_name,
            "coords": f"{coords['lat']}, {coords['lon']}",
            "tz": data.get('timezone_abbreviation', 'UTC'),
            "temp": curr.get('temperature_2m'),
            "feels_like": curr.get('apparent_temperature'),
            "humidity": curr.get('relative_humidity_2m'),
            "pressure_mm": round(curr.get('surface_pressure', 0) * 0.75006),
            "wind": curr.get('wind_speed_10m'),
            "visibility_km": round(curr.get('visibility', 0) / 1000),
            "clouds": curr.get('cloud_cover'),
            "desc": get_weather_description(curr.get('weather_code', 0)),
            "emoji": get_weather_emoji(curr.get('weather_code', 0))
        }
        
        # Недельный прогноз (группировка по Утро/День/Вечер)
        hourly = data.get('hourly', {})
        times = hourly.get('time', [])
        temps = hourly.get('temperature_2m', [])
        hums = hourly.get('relative_humidity', [])
        press = hourly.get('surface_pressure', [])
        codes = hourly.get('weather_code', [])
        
        weekly_forecast = []
        now = datetime.now(timezone.utc)
        
        # Пропускаем прошедшие часы сегодня
        start_idx = 0
        current_hour_str = now.strftime("%Y-%m-%dT%H")
        for i, t in enumerate(times):
            if t.startswith(current_hour_str):
                start_idx = i
                break
        
        # Группируем по дням (следующие 7 дней)
        days_processed = {}
        count = 0
        
        for i in range(start_idx, len(times)):
            if count >= 7 * 3: # 7 дней * 3 слота (утро, день, вечер)
                break
                
            dt_str = times[i] # 2023-10-25T06:00
            dt_obj = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            day_key = dt_obj.strftime("%Y-%m-%d")
            hour = dt_obj.hour
            
            # Определяем слот: Утро (6-11), День (12-17), Вечер (18-23)
            slot_name = ""
            if 6 <= hour <= 11: slot_name = "Утро"
            elif 12 <= hour <= 17: slot_name = "День"
            elif 18 <= hour <= 23: slot_name = "Вечер"
            else: continue # Ночь пропускаем или относим к следующему утру
            
            slot_key = f"{day_key}_{slot_name}"
            
            if slot_key not in days_processed:
                days_processed[slot_key] = {
                    "date": dt_obj.strftime("%d.%m"),
                    "slot": slot_name,
                    "temp": temps[i],
                    "humidity": hums[i],
                    "pressure": round(press[i] * 0.75006),
                    "code": codes[i],
                    "emoji": get_weather_emoji(codes[i])
                }
                count += 1
        
        # Сортируем по дате и времени слота
        sorted_slots = sorted(days_processed.values(), key=lambda x: (x['date'].split('.')[2]+x['date'].split('.')[1]+x['date'].split('.')[0], ["Утро", "День", "Вечер"].index(x['slot'])))
        result['weekly'] = sorted_slots
        
        return result
        
    except Exception as e:
        print(f"Error: {e}")
        return None

def format_current_message(data):
    return (
        f"📍 <b>{data['city']}</b> ({data['coords']})\n"
        f"🕒 TZ: {data['tz']}\n\n"
        f"{data['emoji']} <b>{data['desc']}</b>\n\n"
        f"🌡️ {data['temp']}°C (ощ. {data['feels_like']}°C)\n"
        f"💨 {data['wind']} м/с | 💧 {data['humidity']}%\n"
        f"☁️ {data['clouds']}% | 👁️ {data['visibility_km']} км\n"
        f"📉 {data['pressure_mm']} мм рт. ст.\n\n"
        f"🌙 {get_moon_phase()}"
    )

def format_weekly_message(data):
    lines = [f"📅 <b>Прогноз на неделю ({data['city']})</b>\n"]
    lines.append("<i>Утро (6-11), День (12-17), Вечер (18-23)</i>\n")
    
    for item in data['weekly']:
        # Форматирование с фиксированной шириной для выравнивания
        date_str = f"{item['date']} ({item['slot'][:3]})" # 25.10 (Утр)
        temp_str = f"{item['temp']:>4}°C" # Выравнивание вправо
        hum_str = f"{item['humidity']:>3}%"
        pres_str = f"{item['pressure']:>4}"
        
        line = f"{date_str}: {temp_str} {item['emoji']} | 💧{hum_str} | 📉{pres_str}"
        lines.append(line)
        
    return "\n".join(lines)

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

# --- TELEGRAM HANDLERS ---

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    for city in CITIES.keys():
        markup.add(city)
    
    text = "👋 Привет! Выберите город для прогноза.\nЯ сохраню его для утренней рассылки."
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in CITIES)
def handle_city(message):
    city = message.text
    save_user(message.chat.id, city)
    bot.send_chat_action(message.chat.id, 'typing')
    
    data = get_city_weather_data(city)
    if data:
        text = format_current_message(data)
        markup = telebot.types.InlineKeyboardMarkup()
        btn_week = telebot.types.InlineKeyboardButton("📅 Прогноз на неделю", callback_data=f"weekly_{city}")
        btn_ref = telebot.types.InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{city}")
        markup.add(btn_week, btn_ref)
        
        bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)
        bot.send_message(message.chat.id, "✅ Город сохранен!")
    else:
        bot.send_message(message.chat.id, "❌ Ошибка данных.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('weekly_'))
def handle_weekly(call):
    city = call.data.split('_')[1]
    bot.answer_callback_query(call.id)
    data = get_city_weather_data(city)
    if data:
        text = format_weekly_message(data)
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=text, parse_mode='HTML')
    else:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Ошибка загрузки.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('refresh_'))
def handle_refresh(call):
    city = call.data.split('_')[1]
    bot.delete_message(call.message.chat.id, call.message.message_id)
    # Эмуляция сообщения для вызова handle_city
    fake_msg = type('obj', (object,), {'text': city, 'chat': type('obj', (object,), {'id': call.message.chat.id})})
    handle_city(fake_msg)

# --- РАССЫЛКА ---

def run_morning_broadcast():
    print("🚀 Рассылка...")
    users = load_users()
    for uid, city in users.items():
        data = get_city_weather_data(city)
        if data:
            txt = f"☀️ <b>Доброе утро!</b>\n{format_current_message(data)}"
            try:
                bot.send_message(int(uid), txt, parse_mode='HTML')
                print(f"Sent to {uid}")
            except: pass
    print("Done")

# --- FLASK SERVER ( ДЛЯ ПИНГА ) ---

@app.route('/')
def home():
    return "Weather Bot is Running! 🌤️"

@app.route('/ping')
def ping():
    return jsonify({"status": "ok", "message": "Render is awake!"}), 200

def run_flask():
    app.run(host='0.0.0.0', port=PORT)

# --- ЗАПУСК ---

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--send-morning':
        run_morning_broadcast()
    else:
        print("🤖 Запуск бота + Flask сервера...")
        # Запускаем Flask в отдельном потоке
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        # Запускаем бота в основном потоке
        try:
            bot.infinity_polling()
        except Exception as e:
            print(f"Bot error: {e}")
