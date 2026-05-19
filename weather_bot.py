import os
import sys
import json
import requests
import telebot
from datetime import datetime, timezone, timedelta

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
USERS_FILE = 'users.json'

if not BOT_TOKEN or not WEATHER_API_KEY:
    print("ERROR: Missing env variables.")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN, none_mode=True) # none_mode для скорости в скриптах

CITIES = {
    "Москва": (55.75, 37.61), "Санкт-Петербург": (59.93, 30.33),
    "Казань": (55.79, 49.11), "Новосибирск": (55.00, 82.93),
    "Екатеринбург": (56.84, 60.61), "Нижний Новгород": (56.32, 44.00),
    "Сочи": (43.60, 39.73), "Владивосток": (43.11, 131.88)
}

ICONS = {
    "01d": "☀️", "01n": "🌙", "02d": "⛅", "02n": "☁️", "03d": "☁️", "03n": "☁️",
    "04d": "☁️", "04n": "☁️", "09d": "🌧️", "09n": "🌧️", "10d": "🌦️", "10n": "🌧️",
    "11d": "⛈️", "11n": "⛈️", "13d": "❄️", "13n": "❄️", "50d": "🌫️", "50n": "🌫️"
}

def load_users():
    if not os.path.exists(USERS_FILE): return {}
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def save_user(uid, city):
    users = load_users()
    users[str(uid)] = city
    with open(USERS_FILE, 'w', encoding='utf-8') as f: json.dump(users, f, ensure_ascii=False)

def get_moon_phase():
    known_new = datetime(2001, 1, 1, 12, 24, tzinfo=timezone.utc)
    cycle = 29.53058867
    age = ((datetime.now(timezone.utc) - known_new).total_seconds() / 86400) % cycle
    if age < 1: return "🌑 Новолуние"
    if age < 7: return "🌒 Растущая"
    if age < 8: return "🌓 Первая четверть"
    if age < 14: return "🌔 Растущая"
    if age < 15: return "🌕 Полнолуние"
    if age < 21: return "🌖 Убывающая"
    if age < 22: return "🌗 Последняя четверть"
    return "🌘 Убывающая"

def get_weather(city):
    if city not in CITIES: return None
    lat, lon = CITIES[city]
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code != 200: return None
        d = r.json()
        m = d['main']; w = d['wind']; s = d['sys']; wc = d['weather'][0]
        tz = d['timezone']
        sunrise = datetime.fromtimestamp(s['sunrise'], tz=timezone.utc) + timedelta(seconds=tz)
        sunset = datetime.fromtimestamp(s['sunset'], tz=timezone.utc) + timedelta(seconds=tz)
        
        return (f"☀️ <b>Доброе утро! {city}</b>\n\n"
                f"{ICONS.get(wc['icon'], '🌡️')} <b>{wc['description'].capitalize()}</b>\n"
                f"🌡️ {m['temp']}°C (ощ. {m['feels_like']}°C)\n💨 {w['speed']} м/с\n💧 {m['humidity']}%\n"
                f"📉 {round(m['pressure']*0.75006)} мм рт. ст.\n\n"
                f"🌅 Восход: {sunrise.strftime('%H:%M')} | 🌇 Закат: {sunset.strftime('%H:%M')}\n"
                f"🌙 {get_moon_phase()}")
    except Exception as e:
        print(f"Error {city}: {e}")
        return None

def broadcast():
    print("Starting broadcast...")
    users = load_users()
    if not users: print("No users."); return
    ok = 0
    for uid_str, city in users.items():
        text = get_weather(city)
        if text:
            try:
                bot.send_message(int(uid_str), text, parse_mode='HTML')
                ok += 1
                print(f"Sent to {uid_str}")
            except Exception as e: print(f"Fail {uid_str}: {e}")
    print(f"Done: {ok}/{len(users)}")

# Handlers для интерактивного режима (если запустить локально)
@bot.message_handler(commands=['start'])
def cmd_start(m):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for c in CITIES: kb.add(c)
    bot.send_message(m.chat.id, "Выберите город для утренней рассылки:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in CITIES)
def cmd_city(m):
    save_user(m.chat.id, m.text)
    txt = get_weather(m.text)
    bot.send_message(m.chat.id, txt or "Ошибка погоды.", parse_mode='HTML')
    bot.send_message(m.chat.id, "✅ Город сохранен! Рассылка в 7:30.")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--send-morning':
        broadcast()
    else:
        print("Bot running in polling mode...")
        bot.infinity_polling()
