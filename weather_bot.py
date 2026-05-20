import os
import sys
import json
import requests
import telebot
import math
from datetime import datetime, timezone, timedelta

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
USERS_FILE = 'users.json'

if not BOT_TOKEN or not WEATHER_API_KEY:
    print("❌ ОШИБКА: Не найдены переменные окружения TELEGRAM_BOT_TOKEN или WEATHER_API_KEY")
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

# --- ФУНКЦИИ ПОГОДЫ ---

def get_weather_icon_code(icon_name):
    icons = {
        "01d": "☀️", "01n": "🌙", "02d": "⛅", "02n": "☁️",
        "03d": "☁️", "03n": "☁️", "04d": "☁️", "04n": "☁️",
        "09d": "🌧️", "09n": "🌧️", "10d": "🌦️", "10n": "🌧️",
        "11d": "⛈️", "11n": "⛈️", "13d": "❄️", "13n": "❄️",
        "50d": "🌫️", "50n": "🌫️"
    }
    return icons.get(icon_name, "🌡️")

def get_moon_phase():
    """
    Точный расчет фазы луны на основе юлианской даты.
    Возвращает эмодзи и название фазы.
    """
    now = datetime.now(timezone.utc)
    year = now.year
    month = now.month
    day = now.day

    # Алгоритм расчета фазы (Conway's method / астрономический расчет)
    if month < 3:
        year -= 1
        month += 12
    
    c = 365.25 * year
    e = 30.6 * month
    jd = c + e + day - 694039.09  # Юлианская дата
    jd /= 29.5305882  # Синодический месяц
    
    n = int(jd)
    jd -= n  # Возраст луны в долях цикла (от 0 до 1)
    
    # Определяем фазу в зависимости от возраста (0.0 - Новолуние, 0.5 - Полнолуние)
    # Разбиваем цикл на 8 секторов по 0.125
    phase_map = [
        (0.03, "🌑 Новолуние"),
        (0.12, "🌒 Растущая"),
        (0.16, "🌓 Первая четверть"),
        (0.35, "🌔 Растущая"),
        (0.53, "🌕 Полнолуние"),
        (0.62, "🌖 Убывающая"),
        (0.66, "🌗 Последняя четверть"),
        (1.0, "🌘 Убывающая")
    ]
    
    result_phase = "🌑 Новолуние"
    for threshold, name in phase_map:
        if jd <= threshold:
            result_phase = name
            break
            
    return result_phase

def format_time(timestamp, tz_offset):
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    local_dt = dt + timedelta(seconds=tz_offset)
    return local_dt.strftime("%H:%M")

def get_city_weather(city_name):
    if city_name not in CITIES:
        return None
    coords = CITIES[city_name]
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={coords['lat']}&lon={coords['lon']}&appid={WEATHER_API_KEY}&units=metric&lang=ru"

    try:
        resp = requests.get(url, timeout=10)
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

        text = (
            f"☀️ <b>Доброе утро! Погода в {city_name}</b>\n\n"
            f"{emoji} <b>{desc.capitalize()}</b>\n"
            f"🌡️ {temp}°C (ощущается как {feels_like}°C)\n"
            f"💨 Ветер: {wind_speed} м/с\n"
            f"💧 Влажность: {humidity}%\n"
            f"📉 Давление: {pressure_mm} мм рт. ст.\n\n"
            f"🌅 Восход: {format_time(sunrise_ts, timezone_offset)}\n"
            f"🌇 Закат: {format_time(sunset_ts, timezone_offset)}\n"
            f"🌙 {get_moon_phase()}"
        )
        return text
    except Exception as e:
        print(f"Error fetching weather for {city_name}: {e}")
        return None

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

# --- ЛОГИКА БОТА ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    for city in CITIES.keys():
        markup.add(city)
    bot.send_message(message.chat.id,
        "👋 Привет! Выберите город, чтобы я мог присылать вам утренний прогноз.\n"
        "Также я сохраню ваш выбор для автоматической рассылки в 7:30.",
        reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in CITIES)
def handle_city(message):
    city = message.text
    save_user(message.chat.id, city)
    weather_text = get_city_weather(city)
    if weather_text:
        bot.send_message(message.chat.id, weather_text, parse_mode='HTML')
        bot.send_message(message.chat.id, "✅ Город сохранен! Теперь вы будете получать прогноз каждое утро в 7:30.")
    else:
        bot.send_message(message.chat.id, "Ошибка получения погоды, но город сохранен.")

# --- РЕЖИМ РАССЫЛКИ ---

def run_morning_broadcast():
    print("🚀 Запуск утренней рассылки...")
    users = load_users()
    if not users:
        print("⚠️ Нет пользователей для рассылки.")
        return

    success_count = 0
    for user_id_str, city in users.items():
        user_id = int(user_id_str)
        text = get_city_weather(city)
        if text:
            try:
                bot.send_message(user_id, text, parse_mode='HTML')
                success_count += 1
                print(f"✅ Отправлено пользователю {user_id} ({city})")
            except Exception as e:
                print(f"❌ Ошибка отправки пользователю {user_id}: {e}")
        else:
            print(f"⚠️ Не удалось получить погоду для {city}")

    print(f"🏁 Рассылка завершена. Успешно: {success_count}/{len(users)}")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--send-morning':
        run_morning_broadcast()
    else:
        print("🤖 Запуск бота в режиме ожидания команд...")
        try:
            bot.infinity_polling()
        except Exception as e:
            print(f"Critical bot error: {e}")
