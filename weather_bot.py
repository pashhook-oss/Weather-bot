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
        
        # Новые данные
        visibility_km = round(data.get('visibility', 0) / 1000, 1) # Перевод метров в км
        tz_offset_hours = round(data.get('timezone', 0) / 3600) # Смещение в часах
        
        # Координаты
        lat = data['coord']['lat']
        lon = data['coord']['lon']

        sunrise_ts = data['sys']['sunrise']
        sunset_ts = data['sys']['sunset']
        timezone_offset = data['timezone']

        text = (
            f"☀️ <b>Доброе утро! Погода в {city_name}</b>\n\n"
            f"{emoji} <b>{desc.capitalize()}</b>\n"
            f"🌡️ {temp}°C (ощущается как {feels_like}°C)\n"
            f"💨 Ветер: {wind_speed} м/с\n"
            f"💧 Влажность: {humidity}%\n"
            f"📉 Давление: {pressure_mm} мм рт. ст.\n"
            f"👁️ Видимость: {visibility_km} км\n"
            f"🌧️ Осадки: нет данных в текущем моменте\n\n" # В текущей погоде вероятности осадков нет, только факт
            f"🌅 Восход: {format_time(sunrise_ts, timezone_offset)}\n"
            f"🌇 Закат: {format_time(sunset_ts, timezone_offset)}\n"
            f"🌙 {get_moon_phase()}\n\n"
            f"📍 Координаты: {lat}, {lon}\n"
            f"🕒 Часовой пояс: UTC{tz_offset_hours:+d}"
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
        # Добавляем кнопки для прогноза и обновления
        markup = telebot.types.InlineKeyboardMarkup()
        btn_forecast = telebot.types.InlineKeyboardButton("🕒 Прогноз на 24ч", callback_data=f"forecast_{city}")
        btn_refresh = telebot.types.InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{city}")
        markup.add(btn_forecast, btn_refresh)
        
        bot.send_message(message.chat.id, weather_text, parse_mode='HTML', reply_markup=markup)
        bot.send_message(message.chat.id, "✅ Город сохранен! Теперь вы будете получать прогноз каждое утро в 7:30.")
    else:
        bot.send_message(message.chat.id, "Ошибка получения погоды, но город сохранен.")

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
        
        # Берем первые 8 записей (24 часа)
        for item in forecast_list[:8]:
            dt_txt = item['dt_txt']
            time_str = dt_txt.split()[1][:5] 
            temp = item['main']['temp']
            desc = item['weather'][0]['description']
            
            # Вероятность осадков (POP - Probability of Precipitation)
            pop = item.get('pop', 0) * 100
            
            icon = item['weather'][0]['icon']
            emoji = get_weather_icon_code(icon)
            
            msg_text += f"⏰ <b>{time_str}</b>: {temp}°C {emoji}\n"
            msg_text += f"   {desc.capitalize()}, 🌧️ шанс осадков: {int(pop)}%\n\n"
            
        # Кнопка назад
        markup = telebot.types.InlineKeyboardMarkup()
        btn_back = telebot.types.InlineKeyboardButton("🔙 Назад", callback_data=f"refresh_{city_name}")
        markup.add(btn_back)

        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=msg_text, parse_mode='HTML', reply_markup=markup)
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        print(f"Forecast Error: {e}")
        bot.answer_callback_query(call.id, "Ошибка", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('refresh_'))
def handle_refresh_callback(call):
    city_name = call.data.split('_')[1]
    bot.delete_message(call.message.chat.id, call.message.message_id)
    # Отправляем новое сообщение с погодой
    weather_text = get_city_weather(city_name)
    if weather_text:
        markup = telebot.types.InlineKeyboardMarkup()
        btn_forecast = telebot.types.InlineKeyboardButton("🕒 Прогноз на 24ч", callback_data=f"forecast_{city_name}")
        btn_refresh = telebot.types.InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{city_name}")
        markup.add(btn_forecast, btn_refresh)
        bot.send_message(call.message.chat.id, weather_text, parse_mode='HTML', reply_markup=markup)

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
