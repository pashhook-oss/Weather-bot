import os
import sys
import json
import requests
from datetime import datetime, timezone, timedelta
import telebot

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
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
        51: "Морось", 53: "Морось", 55: "Плотная морось",
        61: "Дождь", 63: "Дождь", 65: "Сильный дождь",
        71: "Снег", 73: "Снег", 75: "Сильный снег",
        80: "Ливень", 81: "Ливень", 82: "Сильный ливень",
        95: "Гроза", 96: "Гроза с градом", 99: "Сильная гроза"
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

# --- ЛОГИКА ПОГОДЫ (OPEN-METEO) ---

def get_city_weather_data(city_name):
    if city_name not in CITIES:
        return None
    
    coords = CITIES[city_name]
    lat = coords['lat']
    lon = coords['lon']
    
    # Запрос: текущая погода + почасовой прогноз на 7 дней (для выборки утро/день/вечер)
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
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
        hourly = data.get('hourly', {})
        
        # Текущие данные
        current_temp = curr.get('temperature_2m')
        feels_like = curr.get('apparent_temperature')
        humidity = curr.get('relative_humidity_2m')
        pressure_hpa = curr.get('surface_pressure')
        pressure_mm = round(pressure_hpa * 0.75006) if pressure_hpa else 0
        wind_speed = curr.get('wind_speed_10m')
        visibility_m = curr.get('visibility')
        visibility_km = round(visibility_m / 1000) if visibility_m else "N/A"
        cloud_cover = curr.get('cloud_cover')
        weather_code = curr.get('weather_code', 0)
        
        # Прогноз на 7 дней (Утро, День, Вечер)
        time_list = hourly.get('time', [])
        temp_list = hourly.get('temperature_2m', [])
        hum_list = hourly.get('relative_humidity_2m', [])
        pres_list = hourly.get('surface_pressure', [])
        code_list = hourly.get('weather_code', [])
        
        forecast_week = []
        
        # Группируем по дням. Берем 7 полных дней начиная с завтра (или сегодня, если еще рано)
        # Для простоты берем срез данных на 7 дней вперед от текущего момента
        # Нам нужны часы: 06:00 (Утро), 12:00 (День), 18:00 (Вечер)
        
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        
        days_processed = 0
        current_date_str = ""
        
        day_data = {}
        
        for i, t_str in enumerate(time_list):
            # t_str формат: "2023-10-27T06:00"
            date_part = t_str.split('T')[0]
            time_part = t_str.split('T')[1] # "06:00"
            
            # Пропускаем прошедшее время сегодня
            if date_part == today_str:
                hour_now = int(time_part.split(':')[0])
                if hour_now < 6: continue # Если сейчас ночь, утро еще впереди, но если уже вечер, то утро прошло
            
            # Начинаем сборку дней
            if date_part != current_date_str:
                if current_date_str and len(day_data) == 3:
                    forecast_week.append(day_data)
                    days_processed += 1
                
                if days_processed >= 7:
                    break
                    
                current_date_str = date_part
                day_data = {}
            
            hour = int(time_part.split(':')[0])
            
            # Собираем слоты
            if hour == 6 and 'morning' not in day_data:
                day_data['morning'] = {
                    'temp': temp_list[i], 'hum': hum_list[i], 
                    'pres': round(pres_list[i] * 0.75006) if pres_list[i] else 0,
                    'code': code_list[i]
                }
            elif hour == 12 and 'day' not in day_data:
                day_data['day'] = {
                    'temp': temp_list[i], 'hum': hum_list[i], 
                    'pres': round(pres_list[i] * 0.75006) if pres_list[i] else 0,
                    'code': code_list[i]
                }
            elif hour == 18 and 'evening' not in day_data:
                day_data['evening'] = {
                    'temp': temp_list[i], 'hum': hum_list[i], 
                    'pres': round(pres_list[i] * 0.75006) if pres_list[i] else 0,
                    'code': code_list[i]
                }
        
        # Добавляем последний день, если он заполнен
        if len(day_data) == 3:
            forecast_week.append(day_data)
            
        # Формируем даты для заголовков дней
        dates = []
        for i in range(len(forecast_week)):
            d = now + timedelta(days=i+1)
            dates.append(d.strftime("%d.%m (%a)")) # "27.10 (Пт)"
            
        return {
            "city": city_name,
            "coords": f"{coords['lat']}, {coords['lon']}",
            "tz": data.get('timezone_abbreviation', 'UTC'),
            "temp": current_temp,
            "feels_like": feels_like,
            "desc": get_weather_description(weather_code),
            "emoji": get_weather_emoji(weather_code),
            "humidity": humidity,
            "pressure_mm": pressure_mm,
            "wind": wind_speed,
            "visibility_km": visibility_km,
            "clouds": cloud_cover,
            "forecast_week": forecast_week,
            "dates": dates
        }
        
    except Exception as e:
        print(f"Error: {e}")
        return None

def format_weekly_forecast(data):
    """Формирует аккуратный текст прогноза на неделю"""
    lines = [f"📅 <b>Прогноз на 7 дней: {data['city']}</b>\n"]
    lines.append("─────────────────────")
    
    for i, day in enumerate(data['forecast_week']):
        date_str = data['dates'][i]
        lines.append(f"\n<b>{date_str}</b>")
        
        # Утро
        m = day.get('morning', {})
        m_emoji = get_weather_emoji(m.get('code', 0))
        lines.append(f"🌅 Утро:  `{m.get('temp', 0):>4}`°C  {m_emoji}  💧{m.get('hum', 0)}%  📉{m.get('pres', 0)}мм")
        
        # День
        d = day.get('day', {})
        d_emoji = get_weather_emoji(d.get('code', 1), is_day=1)
        lines.append(f"☀️ День:  `{d.get('temp', 0):>4}`°C  {d_emoji}  💧{d.get('hum', 0)}%  📉{d.get('pres', 0)}мм")
        
        # Вечер
        e = day.get('evening', {})
        e_emoji = get_weather_emoji(e.get('code', 0), is_day=0)
        lines.append(f"🌇 Вечер: `{e.get('temp', 0):>4}`°C  {e_emoji}  💧{e.get('hum', 0)}%  📉{e.get('pres', 0)}мм")
        
    lines.append("─────────────────────")
    return "\n".join(lines)

def format_current_message(data):
    text = (
        f"📍 <b>{data['city']}</b> ({data['coords']})\n"
        f"🕒 Часовой пояс: {data['tz']}\n\n"
        f"{data['emoji']} <b>{data['desc']}</b>\n\n"
        f"🌡️ Температура: <b>{data['temp']}°C</b> (ощущается {data['feels_like']}°C)\n"
        f"💨 Ветер: {data['wind']} м/с\n"
        f"💧 Влажность: {data['humidity']}%\n"
        f"☁️ Облачность: {data['clouds']}%\n"
        f"👁️ Видимость: {data['visibility_km']} км\n"
        f"📉 Давление: <b>{data['pressure_mm']} мм рт. ст.</b>\n\n"
        f"🌙 Луна: {get_moon_phase()}"
    )
    return text

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
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except:
        pass

# --- БОТ ---

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    for city in CITIES.keys():
        markup.add(city)
    
    text = (
        "👋 Привет! Я бот погоды (<b>Open-Meteo</b>).\n\n"
        "Выберите город из меню ниже:\n"
        "• Прогноз на 7 дней (Утро/День/Вечер)\n"
        "• Точные данные: осадки, давление, влажность\n"
        "• Автоматическая рассылка в 7:30"
    )
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text in CITIES)
def handle_city(message):
    city = message.text
    save_user(message.chat.id, city)
    
    bot.send_chat_action(message.chat.id, 'typing')
    data = get_city_weather_data(city)
    
    if data:
        text = format_current_message(data)
        markup = telebot.types.InlineKeyboardMarkup()
        btn_week = telebot.types.InlineKeyboardButton("📅 Прогноз на 7 дней", callback_data=f"week_{city}")
        btn_refresh = telebot.types.InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{city}")
        markup.add(btn_week, btn_refresh)
        
        bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)
        # bot.send_message(message.chat.id, "✅ Город сохранен!")
    else:
        bot.send_message(message.chat.id, "❌ Ошибка получения данных.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('week_'))
def handle_week_callback(call):
    city = call.data.split('_')[1]
    bot.answer_callback_query(call.id)
    
    data = get_city_weather_data(city)
    if data:
        text = format_weekly_forecast(data)
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=text, parse_mode='HTML')
    else:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Ошибка загрузки прогноза.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('refresh_'))
def handle_refresh_callback(call):
    city = call.data.split('_')[1]
    bot.delete_message(call.message.chat.id, call.message.message_id)
    # Эмуляция сообщения для вызова handle_city
    fake_msg = type('obj', (object,), {'text': city, 'chat': type('obj', (object,), {'id': call.message.chat.id})})
    handle_city(fake_msg)

# --- РАССЫЛКА ---

def run_morning_broadcast():
    print("🚀 Запуск рассылки...")
    users = load_users()
    if not users:
        print("Нет пользователей.")
        return

    for user_id_str, city in users.items():
        data = get_city_weather_data(city)
        if data:
            header = f"☀️ <b>Доброе утро!</b>\nПогода в {data['city']}:\n\n"
            text = header + format_current_message(data)
            try:
                bot.send_message(int(user_id_str), text, parse_mode='HTML')
                print(f"✅ Отправлено {user_id_str}")
            except Exception as e:
                print(f"❌ Ошибка {user_id_str}: {e}")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--send-morning':
        run_morning_broadcast()
    else:
        print("🤖 Бот запущен...")
        bot.infinity_polling()
