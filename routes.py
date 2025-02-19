from flask import Blueprint, request, jsonify
from sqlalchemy.orm import joinedload
import requests
from database import db
from sqlalchemy import func

from models import Client, Appointment, Service, Schedule, Master
from config import Config

from celery.result import AsyncResult
from datetime import datetime, timedelta, time
import pytz
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

main_routes = Blueprint('main', __name__)

def get_day_in_russian(date):
    """Возвращает день недели на русском языке"""
    days = {
        'Monday': 'Понедельник',
        'Tuesday': 'Вторник',
        'Wednesday': 'Среда',
        'Thursday': 'Четверг',
        'Friday': 'Пятница',
        'Saturday': 'Суббота',
        'Sunday': 'Воскресенье'
    }
    return days[date.strftime('%A')]

@main_routes.route('/webhook/', methods=['POST'])
def webhook():
    """Обработчик входящих вебхуков."""
    data = request.get_json()

    if data.get('typeWebhook') == 'incomingMessageReceived':
        chat_id = data['senderData']['chatId']
        
        message_data = data.get('messageData', {})
        
        # Проверка на наличие типа сообщения
        if message_data.get('typeMessage') == 'textMessage':
            message = message_data.get('textMessageData', {}).get('textMessage', '')
            if message:
                handle_client_message(chat_id, message)
            else:
                logger.warning(f"Пустое текстовое сообщение от chatId: {chat_id}")
                send_message(chat_id, "Пожалуйста, введите текстовую команду.")
                
        else:
            logger.info(f"Неподдерживаемый тип сообщения от chatId: {chat_id} (тип: {message_data.get('typeMessage')})")
            send_message(chat_id, "Я обрабатываю только текстовые сообщения. 😊")
            return jsonify({'status': 'unsupported_type'}), 400

    return jsonify({'status': 'received'}), 200

def show_main_menu(phone):
    """Отображение главного меню"""
    menu = (
        "Главное меню:\n"
        "1. 🌐 Информация о нас\n"
        "2. 🗃️ Запись на услугу\n"
        "3. 🎉 Акции\n"
        "4. 🔎 Мои записи\n"
        "5. 🕹️ Связь с администратором\n"
        "0. 🏠 Вернуться в главное меню"
    )
    send_message(phone, menu)

def send_info(client):
    """Отправка информации о салоне"""
    info = (
        "Наш салон красоты:\n"
        "📍 Адрес: ул. Примерная, 123\n"
        "🕒 Часы работы: 9:00-18:00\n"
        "☎️ Телефон: +7 (999) 123-45-67\n"
        "🌟 10 лет успешной работы!"
    )
    send_message(client.phone, info)
    show_main_menu(client.phone)

def send_promotions(client):
    """Отправка информации об акциях"""
    promotions = (
        "Текущие акции:\n"
        "🎁 Скидка 20% на первое посещение\n"
        "👫 Приведи друга - получи скидку 30%\n"
        "💇♀️ Комплекс услуг - скидка 15%"
    )
    send_message(client.phone, promotions)
    show_main_menu(client.phone)

def send_contacts(client):
    """Отправка контактов администратора"""
    contacts = (
        "Связь с администратором:\n"
        "📞 Телефон: +7 (999) 765-43-21\n"
        "✉️ Email: admin@salon.ru\n"
        "📱 WhatsApp: https://wa.me/79997654321"
    )
    send_message(client.phone, contacts)
    show_main_menu(client.phone)

def process_date_selection(client, message):
    """Обработка выбора даты"""
    if message == '0':
        reset_to_main_menu(client)
    elif message == '8':
        client.next_week_start += 1
        show_dates_menu(client)
    elif message == '9':
        if client.next_week_start > 0:
            client.next_week_start -= 1
        show_dates_menu(client)
    else:
        try:
            day_number = int(message)
            if 1 <= day_number <= 7:
                selected_date = calculate_selected_date(client.next_week_start, day_number)
                client.selected_date = selected_date
                client.current_state = 'choosing_time'  # Переходим к выбору времени
                db.session.commit()
                show_time_slots(client)
            else:
                send_message(client.phone, "❌ Выберите число от 1 до 7")
        except ValueError:
            send_message(client.phone, "⚠️ Введите номер варианта")

def calculate_selected_date(week_offset, day_number):
    """Вычисление выбранной даты"""
    base_date = datetime.now().date()
    return base_date + timedelta(
        days=(week_offset * 7) + (day_number - 1)
    )

def show_time_slots(client):
    # Установим часовой пояс "Сахалин"
    tz_sakhalin = pytz.timezone('Asia/Sakhalin')
    current_time = datetime.now(tz_sakhalin)

    service = Service.query.get(client.selected_service_id)
    if not service:
        send_message(client.phone, "❌ Услуга не найдена.")
        return reset_to_main_menu(client)

    schedule = Schedule.query.filter_by(
        master_id=client.selected_master_id,
        date=client.selected_date
    ).first()

    if not schedule:
        send_message(client.phone, "❌ Мастер не работает в эту дату.")
        return show_dates_menu(client)

    # Передаем tz_sakhalin в get_available_time_slots
    available_slots = get_available_time_slots(service, client.selected_date, client.selected_master_id, tz_sakhalin)
    
    client.available_slots = available_slots
    db.session.commit()

    if available_slots:
        menu = ["Выберите время:"]
        for idx, slot in enumerate(available_slots, 1):
            menu.append(f"{idx}. {slot}")
        menu.append("0. Назад")
        send_message(client.phone, "\n".join(menu))
    else:
        send_message(client.phone, "❌ Нет доступного времени для записи.")
        client.current_state = 'choosing_date'
        show_dates_menu(client)


def is_break_time(start, end):
    """Проверка попадания в обеденный перерыв"""
    break_start = datetime.combine(start.date(), time(13, 0))
    break_end = datetime.combine(start.date(), time(14, 0))
    return (start < break_end) and (end > break_start)

def check_time_conflict(new_start, new_end, appointments_data, selected_date):
    """Проверка конфликтов временных интервалов"""
    for app_time, app_duration in appointments_data:
        app_start = datetime.combine(selected_date, app_time)
        app_end = app_start + timedelta(minutes=app_duration)
        
        # Проверка пересечения интервалов
        if (new_start < app_end) and (new_end > app_start):
            return True
    return False


def format_slot(index, start_time, end_time):
    """Форматирование слота времени для вывода"""
    # Преобразуем start_time и end_time в объекты datetime для корректного вычитания
    start_datetime = datetime.combine(datetime.now().date(), start_time)
    end_datetime = datetime.combine(datetime.now().date(), end_time)
    
    # Вычисляем длительность слота
    duration_minutes = (end_datetime - start_datetime).seconds // 60
    
    return f"{index}. {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')} ({duration_minutes} мин)"

def schedule_reminders(appointment):
    from tasks import send_24h_reminder, send_1h_reminder
    from celery_app import celery
    from sqlalchemy.orm.exc import StaleDataError
    # Отмена предыдущих задач
    if appointment.reminder_task_id:
        try:
            celery.control.revoke(appointment.reminder_task_id, terminate=True)
        except Exception as e:
            logger.error(f"Ошибка отмены задачи {appointment.reminder_task_id}: {e}")

    local_tz = pytz.timezone('Asia/Sakhalin')
    naive_datetime = datetime.combine(appointment.date, appointment.time)

    local_datetime = local_tz.localize(naive_datetime)
    reminder_24h = local_datetime - timedelta(hours=24)
    reminder_1h = local_datetime - timedelta(hours=1)

    utc_24h = reminder_24h.astimezone(pytz.utc)
    utc_1h = reminder_1h.astimezone(pytz.utc)

    logger.info(f"Запланированы напоминания для записи {appointment.id}:")
    logger.info(f"  Напоминание за 24 часа: {utc_24h.isoformat()}")
    logger.info(f"  Напоминание за 1 час: {utc_1h.isoformat()}")

    now_utc = datetime.now(pytz.utc)
    
    if utc_24h > now_utc:
        send_24h_reminder.apply_async(args=[appointment.id], eta=utc_24h)
        logger.info("24h reminder scheduled.")
    else:
        logger.warning("Время для 24h напоминания прошло.")
    
    if utc_1h > now_utc:
        send_1h_reminder.apply_async(args=[appointment.id], eta=utc_1h)
        logger.info("1h reminder scheduled.")
    else:
        logger.warning("Время для 1h напоминания прошло.")
    try:
        db.session.commit()
    except StaleDataError:
        db.session.rollback()
        logger.warning("Конфликт версий. Перезагружаем запись...")
        # Явное обновление объекта из БД
        fresh_appointment = db.session.query(Appointment).get(appointment.id)
        if fresh_appointment:
            schedule_reminders(fresh_appointment)

def process_time_selection(client, message):
    """Обработка выбора времени для записи."""
    if message == '0':
        client.current_state = 'choosing_date'
        db.session.commit()
        show_dates_menu(client)
        return

    try:
        time_index = int(message)
        if time_index < 1:
            raise ValueError

        # Установим часовой пояс "Сахалин"
        tz_sakhalin = pytz.timezone('Asia/Sakhalin')

        # Генерируем доступные слоты снова, чтобы убедиться, что они актуальны
        service = Service.query.get(client.selected_service_id)
        available_slots = get_available_time_slots(service, client.selected_date, client.selected_master_id, tz_sakhalin)

        if not available_slots or time_index > len(available_slots):
            send_message(client.phone, "❌ Неверный номер времени")
            return show_time_slots(client)

        selected_time_str = available_slots[time_index - 1]
        selected_time = datetime.strptime(selected_time_str, "%H:%M").time()

        # Создаем запись
        create_appointment(client, selected_time)

        #  Планируем напоминания

    except (ValueError, IndexError):
        send_message(client.phone, "⚠️ Введите корректный номер времени")
        show_time_slots(client)

        
def get_available_masters(service, selected_date):
    """Получение доступных мастеров для услуги на выбранный день."""
    masters = service.masters  # Получаем всех мастеров, привязанных к услуге
    available_masters = []

    for master in masters:
        # Получаем все расписания мастера на выбранную дату
        master_schedule = Schedule.query.filter_by(date=selected_date, master_id=master.id).all()
        
        # Если мастер работает в этот день, проверяем его доступность
        if master_schedule:
            # Проверяем, есть ли уже записи на время мастера
            appointments = Appointment.query.filter(
                Appointment.date == selected_date,
                Appointment.master_id == master.id
            ).all()
            
            # Если нет записей, мастер доступен
            if not appointments:
                available_masters.append(master)

    return available_masters

def is_time_slot_fully_booked(booked_times, schedule, service):
    opening_time = datetime.combine(schedule.date, schedule.opening_time)
    closing_time = datetime.combine(schedule.date, schedule.closing_time)
    
    current_time = opening_time
    slot_duration = timedelta(minutes=service.duration)  # Используем длительность услуги
    
    while current_time + slot_duration <= closing_time:
        slot_end = current_time + slot_duration
        if not any(start <= current_time < end or start < slot_end <= end for start, end in booked_times):
            return False
        current_time = slot_end  # Шаг, например, каждые 15 минут

    return True

def valid_chat_id(chat_id):
    """Проверяет валидность chat_id"""
    return chat_id and (chat_id.endswith('@c.us') or chat_id.endswith('@g.us'))

def handle_client_message(chat_id, message):
    """Основной обработчик сообщений от клиента"""
    client = Client.query.filter_by(phone=chat_id).first()
    
    if not client:
        register_new_client(chat_id)
        return  # Здесь возвращаемся, не вызывая меню сразу
    
    process_client_input(client, message.strip())


def process_client_input(client, message):
    """Роутер обработки сообщений в зависимости от состояния"""
    state_handlers = {
        'expecting_name': handle_name_input,
        'checking_appointments': handle_appointment_check,
        'waiting_for_cancellation': handle_cancellation,
        'active': handle_active_state,
        'choosing_service_category': process_service_category_selection,
        'choosing_sub_service': process_sub_service_selection,
        'choosing_master': process_master_selection,
        'choosing_date': process_date_selection,
        'choosing_time': process_time_selection,
        'choosing_type': process_service_type_selection,
        'awaiting_confirmation': handle_confirmation,
    }
    
    handler = state_handlers.get(client.current_state, handle_unknown_state)
    handler(client, message)

# В файле routes.py
def handle_confirmation(client, message):
    """Обработка подтверждения записи"""
    from celery_app import celery
    try:
        # Ищем ВСЕ записи с pending статусом
        pending_appointments = [a for a in client.future_appointments 
                               if a.confirmation_status == 'pending']
        
        if not pending_appointments:
            send_message(client.phone, "❌ Нет активных записей для подтверждения.")
            return reset_to_main_menu(client)

        # Берем последнюю запись (самую актуальную)
        appointment = pending_appointments[-1]
        logger.info(f"Обработка подтверждения для записи {appointment.id}")

        # Обработка подтверждения
        if message == '1':
            appointment.confirmation_status = 'confirmed'
            # Отменяем ВСЕ задачи напоминаний
            if appointment.reminder_task_id:
                celery.control.revoke(appointment.reminder_task_id, terminate=True)
                logger.info(f"Задача {appointment.reminder_task_id} отменена.")
            send_message(client.phone, "✅ Запись подтверждена! Ждем вас.")
            db.session.commit()
            reset_to_main_menu(client)
        
        elif message == '2':
            show_cancellation_menu(client)
            db.session.commit()
        
        else:
            send_message(client.phone, "⚠️ Пожалуйста, выберите '1' или '2'.")
            return


    except Exception as e:
        logger.error(f"FATAL ERROR: {str(e)}", exc_info=True)
        db.session.rollback()
        send_message(client.phone, "❌ Критическая ошибка. Обратитесь в поддержку.")


def create_appointment(client, selected_time):
    """
    Создает новую запись на услугу.
    """
    if client.selected_date is None:
        send_message(client.phone, "Ошибка: дата не выбрана. Пожалуйста, выберите дату.")
        return
    
    service = Service.query.get(client.selected_service_id)
    selected_master = Master.query.get(client.selected_master_id)
    start_datetime = datetime.combine(client.selected_date, selected_time)
    end_datetime = start_datetime + timedelta(minutes=service.duration)

    # Проверка наличия записи у клиента на выбранную дату
    client_appointments = Appointment.query.filter_by(client_id=client.id, date=client.selected_date).all()
    for app in client_appointments:
        app_start = datetime.combine(app.date, app.time)
        app_end = app_start + timedelta(minutes=app.service.duration)
        # Если интервалы пересекаются
        if not (end_datetime <= app_start or start_datetime >= app_end):
            conflict_msg = (
                "❌ На выбранное время у вас уже есть запись:\n"
                f"{app.service.name} - {selected_master.name} - {app.date.strftime('%d.%m.%Y')} {app.time.strftime('%H:%M')}\n"
                "Пожалуйста, проверьте ваши записи:"
            )
            send_message(client.phone, conflict_msg)
            check_appointments(client)  # Показываем записи клиента
            return  # Не продолжаем создание новой записи
        
    # Получаем все записи мастера на выбранную дату
    appointments = Appointment.query.filter(
        Appointment.date == client.selected_date,
        Appointment.master_id == client.selected_master_id
    ).all()

    # Проверяем, не пересекается ли новый интервал с существующими
    for app in appointments:
        app_start = datetime.combine(app.date, app.time)
        app_end = app_start + timedelta(minutes=app.service.duration)
        if not (end_datetime <= app_start or start_datetime >= app_end):
            send_message(client.phone, "❌ Это время уже занято другим клиентом.")
            return show_time_slots(client)

    # Создаем новую запись
    new_appointment = Appointment(
        client_id=client.id,
        service_id=client.selected_service_id,
        master_id=client.selected_master_id,
        date=client.selected_date,
        time=selected_time,
        status='scheduled',
        confirmation_status='pending'
    )
    db.session.add(new_appointment)
    db.session.commit()

    # Обновляем список занятых интервалов
    appointments = Appointment.query.filter(
        Appointment.date == client.selected_date,
        Appointment.master_id == client.selected_master_id
    ).all()

    busy_intervals = []
    for app in appointments:
        start = app.time.hour * 60 + app.time.minute
        end = start + app.service.duration
        busy_intervals.append({'start': start, 'end': end})

    # Сортируем и объединяем интервалы
    busy_sorted = sorted(busy_intervals, key=lambda x: x['start'])
    merged = []
    for interval in busy_sorted:
        if not merged or interval['start'] > merged[-1]['end']:
            merged.append(interval)
        else:
            merged[-1]['end'] = max(merged[-1]['end'], interval['end'])

    # Отправляем подтверждение клиенту
    confirm_message = (
        f"✅ Запись успешно создана!\n"
        f"👨💼 Мастер: {selected_master.name}\n"
        f"📅 Дата: {client.selected_date.strftime('%d.%m.%Y')}\n"
        f"⏰ Время: {selected_time.strftime('%H:%M')}\n"
        f"💈 Услуга: {service.name}"
    )
    send_message(client.phone, confirm_message)
    schedule_reminders(new_appointment)
    reset_to_main_menu(client)

def round_to_nearest_15_up(dt):
    """Округление времени вверх до ближайшего значения, кратного 15 минутам."""
    # Округляем минуты до следующего 15-минутного интервала
    minutes = (dt.minute // 15) * 15
    if dt.minute % 15 != 0:
        minutes += 15
    
    # Если округление выходит за пределы часа
    if minutes == 60:
        dt += timedelta(hours=1)
        minutes = 0
    
    return dt.replace(minute=minutes, second=0, microsecond=0)

def get_available_time_slots(service, selected_date, master_id, tz_sakhalin):
    """
    Возвращает список доступных временных слотов для записи мастера на услугу.
    """
    schedule = Schedule.query.filter_by(date=selected_date, master_id=master_id).first()
    if not schedule:
        return []

    # Рабочее время мастера
    opening_dt = datetime.combine(selected_date, schedule.opening_time)
    closing_dt = datetime.combine(selected_date, schedule.closing_time)
    service_duration = timedelta(minutes=service.duration)

    opening_dt = tz_sakhalin.localize(opening_dt)
    closing_dt = tz_sakhalin.localize(closing_dt)

    appointments = Appointment.query.filter_by(date=selected_date, master_id=master_id).all()

    busy_intervals = []
    for appointment in appointments:
        app_start = tz_sakhalin.localize(datetime.combine(selected_date, appointment.time))
        app_end = app_start + timedelta(minutes=appointment.service.duration)
        busy_intervals.append((app_start, app_end))
    busy_intervals.sort(key=lambda x: x[0])

    free_intervals = []
    current_time = opening_dt

    for busy_start, busy_end in busy_intervals:
        if current_time < busy_start:
            free_intervals.append((current_time, busy_start))
        current_time = max(current_time, busy_end)

    if current_time < closing_dt:
        free_intervals.append((current_time, closing_dt))

    available_slots = []
    now = datetime.now(tz_sakhalin)

    for free_start, free_end in free_intervals:
        # Пропускаем свободные слоты, которые прошли
        if selected_date == now.date() and free_end <= now:
            continue

        # Округляем текущее время до ближайшего 15-минутного интервала
        slot_start = max(round_to_nearest_15_up(now), free_start) if selected_date == now.date() else free_start

        current_slot = slot_start
        step = timedelta(minutes=15)

        while current_slot + service_duration <= free_end:
            available_slots.append(current_slot.strftime("%H:%M"))
            current_slot += step

    return available_slots


def is_time_conflict(slot_start_time, slot_end_time, app_time, app_duration):
    """Проверка пересечения временных интервалов."""
    app_start_time = app_time
    app_end_time = (datetime.combine(datetime.now().date(), app_time) + timedelta(minutes=app_duration)).time()

    return (slot_start_time < app_end_time and slot_end_time > app_start_time)

def handle_name_input(client, message):
    """Обработка ввода имени при регистрации"""
    client.name = message.title()
    client.current_state = 'active'
    db.session.commit()
    send_message(client.phone, f"Добро пожаловать, {client.name}!")
    show_main_menu(client.phone)

def handle_active_state(client, message):
    """Обработка основного меню"""
    if message.lower() in ["привет", "hi", "hello"]:
        send_message(client.phone, "Чем могу помочь?")
        show_main_menu(client.phone)
    elif message.isdigit() and int(message) in range(6):
        handle_menu_option(client, int(message))
    else:
        send_message(client.phone, "Выберите вариант из меню:")
        show_main_menu(client.phone)

def handle_menu_option(client, option):
    """Обработчик выбора пунктов меню"""
    menu_options = {
        0: lambda: show_main_menu(client.phone),
        1: lambda: send_info(client),
        2: lambda: show_services_menu(client),
        3: lambda: send_promotions(client),
        4: lambda: check_appointments(client),
        5: lambda: send_contacts(client)
    }
    
    if option in menu_options:
        menu_options[option]()
    else:
        send_message(client.phone, "Неверный вариант")
    
    db.session.commit()

# Основные улучшения в логике работы с записями ↓

def check_appointments(client):
    """Показ активных записей клиента"""
    # Используем правильный способ получения данных через SQLAlchemy
    appointments = db.session.query(Appointment).options(
        joinedload(Appointment.master),
        joinedload(Appointment.service)
    ).filter(
        Appointment.client_id == client.id,
        Appointment.date >= datetime.now().date()
    ).order_by(Appointment.date, Appointment.time  # Добавлена сортировка
    ).all()
    
    if not appointments:
        send_message(client.phone, "❌ У вас нет активных записей")
        return reset_to_main_menu(client)
        
    response = ["📅 Ваши записи🤗:"]
    response += [f"{i+1}. {a.service.name} - {a.master.name} - {a.date.strftime('%d.%m.%Y')} {a.time.strftime('%H:%M')}" 
                for i, a in enumerate(appointments)]
    response.append("\n0. Назад\n1. Отменить запись")
    
    send_message(client.phone, "\n".join(response))
    client.current_state = 'checking_appointments'
    db.session.commit()


def handle_appointment_check(client, message):
    """Обработка действий в режиме просмотра записей"""
    if message == '0':
        reset_to_main_menu(client)
    elif message == '1':
        show_cancellation_menu(client)
    else:
        send_message(client.phone, "Выберите 0 или 1")

def show_cancellation_menu(client):
    """Показ меню отмены с актуальными данными из БД"""
    appointments = client.future_appointments
    if not appointments:
        send_message(client.phone, "❌ У вас нет назначенных записей для отмены.")
        return reset_to_main_menu(client)
    
    response = ["🔻 Выберите запись для отмены:"]
    response += [f"{i+1}. {a.service.name} - {a.date.strftime('%d.%m.%Y')} - {a.time.strftime('%H:%M')}" 
                for i, a in enumerate(appointments)]
    response.append("0. В главное меню")
    
    send_message(client.phone, "\n".join(response))
    client.current_state = 'waiting_for_cancellation'
    db.session.commit()

def delete_appointment(appointment):
    """Удаление записи с базы данных."""
    db.session.delete(appointment)
    db.session.commit()


def notify_client(client, message):
    """Отправка сообщения клиенту."""
    send_message(client.phone, message)


def handle_cancellation(client, message):
    """Обработка отмены записи с валидацией"""
    appointments = client.future_appointments

    if message == '0':  # Если клиент выбрал вернуться в главное меню
        reset_to_main_menu(client)
        return

    try:
        # Преобразуем введённое сообщение в индекс
        index = int(message) - 1
        if 0 <= index < len(appointments):
            appointment = appointments[index]
            delete_appointment(appointment)

            notify_client(client, "✅ Запись успешно отменена! Время стало доступным для других клиентов.")

            # Обновляем список записей клиента
            updated_appointments = Appointment.query.filter(
                Appointment.client_id == client.id,
                Appointment.date >= datetime.now().date()
            ).all()

            # Вместо присвоения используем обновление через метод
            client.future_appointments[:] = updated_appointments
            db.session.commit()

            if updated_appointments:
                check_appointments(client)
            else:
                notify_client(client, "✅ Все записи отменены!")
                reset_to_main_menu(client)
        else:
            notify_client(client, "❌ Неверный номер записи")
    except (ValueError, IndexError):
        notify_client(client, "⚠️ Введите корректный номер записи")



def cancel_appointment(client, index):
    """Удаление записи с подтверждением"""
    try:
        appointment = client.future_appointments[index]
        delete_appointment(appointment)
        
        # Обновляем список записей
        client.future_appointments = Appointment.query.filter(
            Appointment.client_id == client.id,
            Appointment.date >= datetime.now().date()
        ).all()
        
        if client.future_appointments:
            notify_client(client, "✅ Запись успешно отменена!")
            show_cancellation_menu(client.phone)
        else:
            notify_client(client, "✅ Все записи отменены!")
            reset_to_main_menu(client.phone)
            
    except Exception as e:
        print(f"Ошибка отмены: {e}")
        notify_client(client, "❌ Ошибка при отмене записи")


def reset_to_main_menu(client):
    """Сброс состояния и очистка временных данных"""
    client.current_state = 'active'
    client.selected_service_id = None
    client.selected_date = None
    client.next_week_start = 0
    db.session.commit()
    show_main_menu(str(client.phone))

# Остальные функции с улучшениями ↓

def show_services_menu(client):
    """Показ меню основных категорий услуг"""
    main_services = Service.query.filter(Service.parent_service_id == None).all()
    
    menu = ["Выберите категорию услуг:"]
    for idx, service in enumerate(main_services, 1):
        menu.append(f"{idx}. {service.name}")
    menu.append("0. Назад")
    
    send_message(client.phone, "\n".join(menu))
    client.current_state = 'choosing_service_category'
    db.session.commit()

def show_service_types_menu(client):
    """Показ типов услуг"""
    service_types = Service.query.filter(Service.parent_service_id.isnot(None)).all()
    
    if not service_types:
        send_message(client.phone, "⚠️ Типы услуг временно недоступны")
        return reset_to_main_menu(client)
        
    menu = ["Выберите тип услуги:"]
    for idx, service in enumerate(service_types, 1):
        menu.append(f"{idx}. {service.name}")  # Отображает название типа услуги
    menu.append("0. Назад")
    
    send_message(client.phone, "\n".join(menu))
    client.current_state = 'choosing_type'
    db.session.commit()

def process_service_type_selection(client, message):
    """Обработка выбора типа услуги"""
    if message == '0':
        reset_to_main_menu(client)
        return
    
    try:
        type_idx = int(message) - 1
        service_types = Service.query.filter(Service.parent_service_id.isnot(None)).all()
        
        if 0 <= type_idx < len(service_types):
            client.selected_service_category = service_types[type_idx].id
            show_specific_services_menu(client)
        else:
            raise ValueError
    except ValueError:
        send_message(client.phone, "❌ Неверный выбор типа услуги")
        show_service_types_menu(client)


# Исправления в обработке услуг
def process_service_category_selection(client, message):
    """Обработка выбора категории услуг"""
    if message == '0':
        reset_to_main_menu(client)
        return
    
    try:
        service_idx = int(message) - 1
        main_services = Service.query.filter(Service.parent_service_id == None).all()
        
        if 0 <= service_idx < len(main_services):
            client.selected_service_category = main_services[service_idx].id
            client.current_state = 'choosing_sub_service'
            db.session.commit()
            show_sub_services_menu(client)
        else:
            raise ValueError("Выбран неверный индекс услуги.")
    except ValueError as e:
        print(f"Ошибка выбора услуги: {e}")
        send_message(client.phone, "❌ Неверный выбор услуги")
        show_services_menu(client)

def show_sub_services_menu(client):
    """Показ подуслуг выбранной категории"""
    sub_services = Service.query.filter(Service.parent_service_id == client.selected_service_category).all()
    
    # Добавить отладочные сообщения

    if not sub_services:
        send_message(client.phone, "⚠️ Нет доступных услуг в этой категории")
        return reset_to_main_menu(client)

    menu = ["Выберите услугу:"]
    # Исправлено: нумерация с 1, а не с 0
    for idx, service in enumerate(sub_services, 1):
        duration = f"{service.duration} мин." if service.duration < 60 else f"{service.duration // 60} ч. {service.duration % 60} мин."
        menu.append(f"{idx}. {service.name} - {service.price} руб. ({duration})")
    menu.append("0. Назад")
    
    send_message(client.phone, "\n".join(menu))
    client.current_state = 'choosing_sub_service'
    db.session.commit()

def process_sub_service_selection(client, message):
    if message == '0':
        show_services_menu(client)
        return
    
    try:
        service_idx = int(message)
        sub_services = Service.query.filter(
            Service.parent_service_id == client.selected_service_category
        ).all()
        
        if 1 <= service_idx <= len(sub_services):
            service = sub_services[service_idx - 1]
            client.selected_service_id = service.id
            client.current_state = 'choosing_master'
            db.session.commit()
            show_masters_menu(client)
        else:
            send_message(client.phone, "⚠️ Введите номер из списка")
            show_sub_services_menu(client)
    
    except ValueError:
        send_message(client.phone, "⚠️ Введите корректный номер подуслуги")
        show_sub_services_menu(client)


def check_master_availability(master, selected_date):
    """Проверка доступности мастера в выбранный день."""
    appointments = Appointment.query.filter(
        Appointment.date == selected_date,
        Appointment.master_id == master.id
    ).all()
    
    return not appointments 

def show_specific_services_menu(client):
    """Показ услуг внутри выбранной категории"""
    services = Service.query.filter_by(category=client.selected_service_category).all()
    if not services:
        send_message(client.phone, "⚠️ Услуги временно недоступны")
        return reset_to_main_menu(client)
        
    menu = ["Выберите услугу:"]
    for service in services:
        duration = f"{service.duration//60} ч. {service.duration%60} мин." if service.duration >= 60 else f"{service.duration} мин."
        menu.append(f"{service.id}. {service.name} ({service.price} руб., {duration})")
    menu.append("0. Назад")
    
    send_message(client.phone, "\n".join(menu))

def show_masters_menu(client):
    """Показ мастеров для выбранной подуслуги."""
    service = Service.query.get(client.selected_service_id)
    if not service:
        send_message(client.phone, "❌ Услуга не найдена.")
        return reset_to_main_menu(client)
    
    masters = service.masters
    logger.info(f"Доступные мастера для услуги {service.name}: {[m.name for m in masters]}")
    
    if not masters:
        send_message(client.phone, "❌ Нет доступных мастеров.")
        return reset_to_main_menu(client)
    
    menu = ["Выберите мастера:"]
    for idx, master in enumerate(masters, 1):
        menu.append(f"{idx}. {master.name}")
    menu.append("0. Назад")
    
    send_message(client.phone, "\n".join(menu))
    client.current_state = 'choosing_master'
    db.session.commit()


def process_master_selection(client, message):
    """Обработка выбора мастера."""
    logger.info(f"Ввод пользователя (выбор мастера): '{message}'")
    message_clean = message.strip()
    
    if message_clean == '0':
        client.current_state = 'choosing_sub_service'
        db.session.commit()
        show_sub_services_menu(client)
        return

    try:
        selected_index = int(message_clean)
    except ValueError as e:
        logger.error(f"Ошибка преобразования ввода в число: {e}")
        send_message(client.phone, "⚠️ Введите корректный номер мастера")
        return show_masters_menu(client)

    if selected_index < 1:
        send_message(client.phone, "⚠️ Введите корректный номер мастера")
        return show_masters_menu(client)

    service = Service.query.get(client.selected_service_id)
    if not service:
        send_message(client.phone, "❌ Услуга не найдена.")
        return reset_to_main_menu(client)
    
    # Принудительное обновление данных по услуге
    db.session.refresh(service)
    available_masters = service.masters
    logger.info(f"Доступные мастера: {[m.name for m in available_masters]}")

    if not available_masters:
        send_message(client.phone, "❌ Нет доступных мастеров.")
        return reset_to_main_menu(client)

    if 1 <= selected_index <= len(available_masters):
        selected_master = available_masters[selected_index - 1]
        logger.info(f"Выбран мастер: {selected_master.name} (ID: {selected_master.id})")
        
        client.selected_master_id = selected_master.id
        client.current_state = 'choosing_date'
        db.session.commit()
        show_dates_menu(client)
    else:
        send_message(client.phone, "❌ Неверный выбор мастера. Пожалуйста, выберите номер из списка.")
        show_masters_menu(client)


def show_dates_menu(client):
    # Установим часовой пояс "Сахалин"
    tz_sakhalin = pytz.timezone('Asia/Sakhalin')
    current_time = datetime.now(tz_sakhalin)
    today = current_time.date()

    dates = generate_date_range(client.next_week_start, tz_sakhalin)
    
    menu = ["Выберите дату:"]
    
    for idx, date_str in enumerate(dates, 1):
        # Получаем часть строки с датой (формат: "09.02.2025")
        date_part = date_str.split()[0]

        try:
            # Преобразуем только дату, без дня недели
            date_obj = datetime.strptime(date_part, "%d.%m.%Y").date()
        except ValueError as e:
            logger.error(f"Ошибка преобразования даты из строки {date_str}: {e}")
            continue

        if date_obj < today:
            continue  # Пропускаем прошедшие даты

        # Проверка рабочего расписания
        schedule = Schedule.query.filter_by(date=date_obj).first()
        status = "Рабочий день" if schedule and schedule.is_working_day else "Выходной"

        # Формируем меню с корректной нумерацией
        menu.append(f"{idx}. {date_str} - {status}")

    # Добавляем дополнительные опции
    menu += ["8. Следующие даты", "9. Предыдущие даты", "0. Назад"]

    # Отправляем сообщение пользователю
    send_message(client.phone, "\n".join(menu))
    db.session.commit()

def generate_date_range(week_offset, tz_sakhalin):
    """Генерация списка дат с учётом часового пояса."""
    base_date = datetime.now(tz_sakhalin).date()  # Используем текущую дату с учётом часового пояса
    start_date = base_date + timedelta(days=week_offset * 7)
    
    dates = []
    for i in range(7):
        current_date = start_date + timedelta(days=i)
        date_str = f"{current_date.strftime('%d.%m.%Y')} ({get_day_in_russian(current_date)})"
        dates.append(date_str)
    
    return dates

def handle_unknown_state(client, message):
    """Обработка неизвестного состояния"""
    send_message(client.phone, "⚠️ Системная ошибка. Возврат в меню")
    reset_to_main_menu(client)

def register_new_client(chat_id):
    """Регистрация нового клиента"""
    existing_client = Client.query.filter_by(phone=chat_id).first()
    if not existing_client:
        new_client = Client(
            phone=chat_id,
            current_state='expecting_name',
            name=''  # Изменим на явное указание пустого имени для нового клиента
        )
        db.session.add(new_client)
        db.session.commit()
        send_message(chat_id, "Добро пожаловать! Как вас зовут?")
    else:
        send_message(chat_id, "Вы уже зарегистрированы.")

def send_message(chat_id, text):
    """Отправка сообщения через API."""
    if not chat_id or not text:
        logger.warning("Необходимо указать chat_id и текст сообщения.")
        return
    
    try:
        response = requests.post(
            f"{Config.apiUrl}/waInstance{Config.idInstance}/SendMessage/{Config.apiTokenInstance}",
            json={"chatId": chat_id, "message": text}
        )
        response.raise_for_status()  # Проверяем на HTTP ошибки

        logger.info(f"Сообщение успешно отправлено в чат {chat_id}.")
    
    except requests.HTTPError as http_err:
        logger.error(f"HTTP ошибка при отправке сообщения в чат {chat_id}: {http_err.response.status_code} - {http_err.response.text}")
    
    except requests.RequestException as req_err:
        logger.error(f"Ошибка запроса при отправке сообщения в чат {chat_id}: {req_err}")
    
    except Exception as e:
        logger.error(f"Произошла ошибка при отправке сообщения в чат {chat_id}: {str(e)}")