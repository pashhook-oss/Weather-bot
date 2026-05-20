import os
import sys
import json
import requests
import io
from datetime import datetime, timezone, timedelta
import telebot
from telebot import types

# Проверка наличия matplotlib (может отсутствовать в легковесных средах)
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.font_manager import FontProperties
    # Настройка стиля для темной темы (опционально)
    plt.style.use('seaborn-v0_8-darkgrid') 
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("⚠️ Warning: Matplotlib not found. Graphs will be disabled.")

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

# --- ЛОГИКА ПОГОДЫ (OPEN-METEO) ---

def get_city_weather_data(city_name, forecast_hours=24):
    if city_name not in CITIES:
        return None
    
    coords = CITIES[city_name]
    lat = coords['lat']
    lon = coords['lon']
    
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,"
        f"surface_pressure,wind_speed_10m,visibility,cloud_cover"
        f"&hourly=temperature_2m,weather_code,precipitation_probability,precipitation"
        f"&timezone=auto"
    )
    
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        
        data = resp.json()
        curr = data.get('current', {})
        
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
        
        # Прогноз
        hourly = data.get('hourly', {})
        time_list = hourly.get('time', [])
        temp_list = hourly.get('temperature_2m', [])
        code_list = hourly.get('weather_code', [])
        precip_prob_list = hourly.get('precipitation_probability', [])
        precip_amt_list = hourly.get('precipitation', [])
        
        forecast_data = []
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
        
        start_index = 0
        for i, t in enumerate(time_list):
            if t.startswith(now_iso[:13]):
                start_index = i
                break
        
        count = 0
        for i in range(start_index, len(time_list)):
            if count >= 24: break
            t_str = time_list[i].split('T')[1][:5]
            
            forecast_data.append({
                "time": t_str,
                "temp": temp_list[i],
                "code": code_list[i],
                "prob": precip_prob_list[i],
                "amount": precip_amt_list[i],
                "iso_time": time_list[i] # Сохраняем полное время для графика
            })
            count += 1
            
        return {
            "city": city_name,
            "coords": f"{lat}, {lon}",
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
            "forecast": forecast_data
        }
        
    except Exception as e:
        print(f"Error fetching Open-Meteo: {e}")
        return None

def format_current_message(data):
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

def generate_weather_graph(data):
    """Генерирует график температуры и осадков"""
    if not MATPLOTLIB_AVAILABLE:
        return None
    
    try:
        forecast = data['forecast']
        times = [item['iso_time'] for item in forecast]
        temps = [item['temp'] for item in forecast]
        probs = [item['prob'] for item in forecast]
        
        # Парсинг времени для оси X
        dates = [datetime.fromisoformat(t) for t in times]
        
        fig, ax1 = plt.subplots(figsize=(10, 6))
        
        # График температуры (линия)
        color = 'tab:red'
        ax1.set_xlabel('Время')
        ax1.set_ylabel('Температура (°C)', color=color)
        ax1.plot(dates, temps, color=color, marker='o', label='Температура')
        ax1.tick_params(axis='y', labelcolor=color)
        ax1.grid(True, linestyle='--', alpha=0.7)
        
        # График вероятности осадков (столбцы на второй оси)
        ax2 = ax1.twinx()
        color = 'tab:blue'
        ax2.set_ylabel('Вероятность осадков (%)', color=color)
        ax2.bar(dates, probs, color=color, alpha=0.3, width=0.03, label='Осадки %')
        ax2.tick_params(axis='y', labelcolor=color)
        ax2.set_ylim(0, 100)
        
        # Форматирование оси времени
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax1.xaxis.set_major_locator(mdates.HourLocator(interval=3))
        plt.xticks(rotation=45)
        
        # Заголовок
        plt.title(f"Прогноз погоды: {data['city']} (24 часа)", fontsize=14, fontweight='bold')
        
        # Сохранение в буфер
        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        plt.close(fig)
        
        return buf
    except Exception as e:
        print(f"Error generating graph: {e}")
        return None

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

# --- ОБРАБОТЧИКИ БОТА ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for city in CITIES.keys():
        markup.add(city)
    bot.send_message(message.chat.id,
        "👋 Привет! Я бот погоды на базе <b>Open-Meteo</b>.\n\n"
        "Выберите город для прогноза с графиками!",
        reply_markup=markup, parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text in CITIES)
def handle_city(message):
    city = message.text
    save_user(message.chat.id, city)
    
    bot.send_chat_action(message.chat.id, 'typing')
    data = get_city_weather_data(city)
    
    if data:
        text = format_current_message(data)
        markup = types.InlineKeyboardMarkup()
        btn_forecast = types.InlineKeyboardButton("📝 Список на 24ч", callback_data=f"list_{city}")
        btn_graph = types.InlineKeyboardButton("📊 График погоды", callback_data=f"graph_{city}")
        btn_refresh = types.InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{city}")
        markup.add(btn_forecast, btn_graph)
        markup.add(btn_refresh)
        
        bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "❌ Ошибка получения данных.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('list_'))
def handle_list_callback(call):
    city = call.data.split('_')[1]
    data = get_city_weather_data(city)
    if data:
        lines = [f"🕒 <b>Прогноз по часам ({city})</b>\n"]
        for item in data['forecast']:
            emoji = get_weather_emoji(item['code'])
            line = f"⏰ <b>{item['time']}</b>: {item['temp']}°C {emoji}"
            if item['prob'] > 0:
                line += f"\n   💧 {item['prob']}%"
            lines.append(line)
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                              text="\n".join(lines), parse_mode='HTML')
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('graph_'))
def handle_graph_callback(call):
    city = call.data.split('_')[1]
    bot.answer_callback_query(call.id, "Генерирую график...")
    
    data = get_city_weather_data(city)
    if data and MATPLOTLIB_AVAILABLE:
        img_buf = generate_weather_graph(data)
        if img_buf:
            bot.send_photo(call.message.chat.id, photo=img_buf, caption=f"📊 Визуальный прогноз для {city}")
            img_buf.close()
        else:
            bot.reply_to(call.message, "❌ Не удалось создать график.")
    else:
        bot.reply_to(call.message, "❌ Ошибка данных или модуль графиков недоступен.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('refresh_'))
def handle_refresh_callback(call):
    city = call.data.split('_')[1]
    bot.delete_message(call.message.chat.id, call.message.message_id)
    # Эмуляция сообщения выбора города
    msg = type('obj', (object,), {'text': city, 'chat': type('obj', (object,), {'id': call.message.chat.id})})
    handle_city(msg)

# --- РАССЫЛКА ---

def run_morning_broadcast():
    print("🚀 Запуск рассылки...")
    users = load_users()
    for user_id_str, city in users.items():
        data = get_city_weather_data(city)
        if data:
            text = f"☀️ <b>Доброе утро!</b>\n{format_current_message(data)}"
            try:
                bot.send_message(int(user_id_str), text, parse_mode='HTML')
            except:
                pass
    print("✅ Готово.")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--send-morning':
        run_morning_broadcast()
    else:
        print("🤖 Запуск бота...")
        bot.infinity_polling()
