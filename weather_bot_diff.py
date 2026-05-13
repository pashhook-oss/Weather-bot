--- weather_bot.py (原始)


+++ weather_bot.py (修改后)
import telebot
import requests
import datetime
from telebot import types

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = '8833502523:AAE62skdOoe9ZvSEseYiHH9rxbbyPaK-iT0'
API_KEY = '482adb12c18eaf2ee9c6a2dac8e6c7b3'

bot = telebot.TeleBot(BOT_TOKEN)

# Список городов для выбора
CITIES = {
    'Москва': {'lat': 55.7558, 'lon': 37.6173},
    'Санкт-Петербург': {'lat': 59.9343, 'lon': 30.3351},
    'Казань': {'lat': 55.7961, 'lon': 49.1064},
    'Новосибирск': {'lat': 55.0084, 'lon': 82.9357},
    'Екатеринбург': {'lat': 56.8389, 'lon': 60.6057},
    'Нижний Новгород': {'lat': 56.2965, 'lon': 43.9361},
    'Сочи': {'lat': 43.6028, 'lon': 39.7342},
    'Владивосток': {'lat': 43.1198, 'lon': 131.8869}
}

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_weather_data(lat, lon):
    """Получает данные о погоде и прогнозе от OpenWeatherMap"""
    urls = [
        f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={API_KEY}&units=metric&lang=ru",
        f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={API_KEY}&units=metric&lang=ru"
    ]

    results = []
    for url in urls:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                results.append(response.json())
            else:
                return None, None
        except Exception:
            return None, None

    if len(results) == 2:
        return results[0], results[1]
    return None, None

def get_moon_phase():
    """Рассчитывает фазу луны"""
    date = datetime.datetime.now()
    year = date.year
    month = date.month
    day = date.day

    if month < 3:
        year -= 1
        month += 12

    a = int(year / 100)
    b = int(a / 4)
    c = 2 - a + b
    e = int(365.25 * (year + 4716))
    f = int(30.6001 * (month + 1))
    jd = c + day + e + f - 1524.5
    days_since_new = jd - 2451550.1

    new_moons = int(days_since_new / 29.53)
    moon_age = days_since_new - (new_moons * 29.53)

    phase = round(moon_age / 29.53 * 8) % 8

    phases = {
        0: ("🌑", "Новолуние"),
        1: ("🌒", "Растущая луна"),
        2: ("🌓", "Первая четверть"),
        3: ("🌔", "Растущая луна"),
        4: ("🌕", "Полнолуние"),
        5: ("🌖", "Убывающая луна"),
        6: ("🌗", "Последняя четверть"),
        7: ("🌘", "Убывающая луна")
    }
    return phases.get(phase, ("❓", "Неизвестно"))

def format_time(timestamp, tz_offset):
    """Форматирует Unix timestamp в строку времени с учетом часового пояса"""
    dt = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone(datetime.timedelta(seconds=tz_offset)))
    return dt.strftime('%H:%M')

def build_current_message(city_name, data):
    """Формирует сообщение с текущей погодой и доп. данными"""
    main = data['main']
    weather = data['weather'][0]
    wind = data['wind']
    sys = data['sys']

    temp = main['temp']
    feels_like = main['feels_like']
    humidity = main['humidity']
    pressure_hpa = main['pressure']
    pressure_mm = round(pressure_hpa * 0.75006)  # Конвертация в мм рт.ст.

    desc = weather['description'].capitalize()

    # Восход и закат
    sunrise_ts = sys.get('sunrise', 0)
    sunset_ts = sys.get('sunset', 0)
    timezone_offset = data.get('timezone', 0)

    sunrise_str = format_time(sunrise_ts, timezone_offset)
    sunset_str = format_time(sunset_ts, timezone_offset)

    # Луна
    moon_icon, moon_text = get_moon_phase()

    text = (
        f"📍 <b>{city_name}</b>\n\n"
        f"🌡 <b>{temp:.1f}°C</b> ({desc})\n"
        f"💧 Ощущается как: {feels_like:.1f}°C\n"
        f"💨 Ветер: {wind.get('speed', 0):.1f} м/с\n"
        f"📉 Давление: {pressure_mm} мм рт.ст.\n"
        f"💧 Влажность: {humidity}%\n\n"
        f"🌅 Восход: {sunrise_str}\n"
        f"🌇 Закат: {sunset_str}\n"
        f"🌙 Луна: {moon_text} {moon_icon}"
    )
    return text

def build_hourly_message(forecast_data):
    """Формирует сообщение с прогнозом по времени"""
    if not forecast_data or 'list' not in forecast_
        return "Нет данных для прогноза."

    items = forecast_data['list'][:8]  # Берем первые 8 записей (на 24 часа при шаге 3ч)

    lines = ["<b>🕒 Прогноз на 24 часа:</b>\n"]

    for item in items:
        dt_txt = item['dt_txt']
        time_str = dt_txt.split()[1][:5]  # Берем только время ЧЧ:ММ
        temp = item['main']['temp']
        desc = item['weather'][0]['description']
        pop = item.get('pop', 0) * 100  # Вероятность осадков

        lines.append(f"{time_str} | {temp:.1f}°C | {desc.capitalize()} | 💧{pop:.0f}%")

    lines.append("\n<i>*Данные предоставляются с шагом 3 часа (бесплатный тариф API)</i>")

    return "\n".join(lines)

# --- ОБРАБОТЧИКИ БОТА ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [types.InlineKeyboardButton(city, callback_data=f"city:{city}") for city in CITIES.keys()]
    markup.add(*buttons)

    bot.send_message(
        message.chat.id,
        "Привет! Выберите город для получения прогноза погоды:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('city:'))
def handle_city_select(call):
    city_name = call.data.split(':')[1]
    coords = CITIES.get(city_name)

    if not coords:
        bot.answer_callback_query(call.id, "Город не найден", show_alert=True)
        return

    bot.answer_callback_query(call.id, f"Загружаю погоду для {city_name}...")

    current_data, forecast_data = get_weather_data(coords['lat'], coords['lon'])

    if not current_
        bot.send_message(call.message.chat.id, "Ошибка получения данных. Попробуйте позже.")
        return

    # Отправляем основное сообщение с кнопками
    markup = types.InlineKeyboardMarkup()
    btn_refresh = types.InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh:{city_name}")
    btn_hourly = types.InlineKeyboardButton("🕒 Прогноз на 24ч", callback_data=f"hourly:{city_name}")
    markup.add(btn_refresh, btn_hourly)

    msg_text = build_current_message(city_name, current_data)

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=msg_text,
        reply_markup=markup,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('hourly:'))
def handle_hourly_forecast(call):
    city_name = call.data.split(':')[1]
    coords = CITIES.get(city_name)

    if not coords:
        return

    _, forecast_data = get_weather_data(coords['lat'], coords['lon'])

    if not forecast_
        bot.answer_callback_query(call.id, "Ошибка загрузки прогноза", show_alert=True)
        return

    hourly_text = build_hourly_message(forecast_data)

    # Возвращаем кнопку назад
    markup = types.InlineKeyboardMarkup()
    btn_back = types.InlineKeyboardButton("⬅️ Назад к текущей", callback_data=f"city:{city_name}")
    markup.add(btn_back)

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=hourly_text,
        reply_markup=markup,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('refresh:'))
def handle_refresh(call):
    city_name = call.data.split(':')[1]
    handle_city_select(call)

# Запуск бота
if __name__ == '__main__':
    print("Бот запущен...")
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"Ошибка: {e}")