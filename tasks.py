# tasks.py
from flask import current_app
from celery_app import celery
from datetime import datetime, timedelta
from celery import shared_task  # Используем shared_task
from models import Appointment
from database import db
from routes import send_message
import pytz
import logging


logger = logging.getLogger(__name__)


def get_local_timezone():
    return pytz.timezone('Asia/Sakhalin')


# В файле tasks.py
@celery.task(name='tasks.send_24h_reminder')
def send_24h_reminder(appointment_id):
    logger.info(f"[24h] Запуск задачи для записи {appointment_id}")
    with current_app.app_context():
        try:
            appointment = Appointment.query.get(appointment_id)
            if not appointment:
                logger.error(f"[24h] Запись {appointment_id} не найдена.")
                return
            
            # Отправляем сообщение
            _send_reminder(appointment_id, 24)
            
            # Планируем 1h напоминание
            local_tz = get_local_timezone()
            naive_datetime = datetime.combine(appointment.date, appointment.time)
            appointment_time = local_tz.localize(naive_datetime)
            reminder_1h_time = appointment_time - timedelta(hours=1)
            utc_1h = reminder_1h_time.astimezone(pytz.utc)
            
            task = send_1h_reminder.apply_async(args=[appointment_id], eta=utc_1h)
            appointment.reminder_task_id = task.id
            db.session.commit()
            logger.info(f"[24h] 1h задача запланирована: {task.id}")
            
        except Exception as e:
            logger.error(f"[24h] Ошибка: {str(e)}", exc_info=True)
            db.session.rollback()

@celery.task(name='tasks.send_1h_reminder')
def send_1h_reminder(appointment_id):
    logger.info(f"[1h] Запуск задачи для записи {appointment_id}")
    with current_app.app_context():
        try:
            _send_reminder(appointment_id, 1)
        except Exception as e:
            logger.error(f"[1h] Ошибка: {str(e)}", exc_info=True)

def _send_reminder(appointment_id, hours_until):
    try:
        appointment = Appointment.query.get(appointment_id)
        if not appointment:
            logger.error(f"Запись {appointment_id} не найдена.")
            return

        # Проверка статуса перед отправкой
        if appointment.confirmation_status != 'pending':
            logger.info(f"Запись {appointment_id} уже обработана.")
            return

        # Корректное время с часовым поясом
        local_tz = get_local_timezone()
        appointment_time = local_tz.localize(
            datetime.combine(appointment.date, appointment.time)
        )
        # Проверяем, не истекло ли время отправки напоминания
        if datetime.now(local_tz) >= appointment_time:
            logger.warning(f"Время для {hours_until}-часового напоминания прошло для записи {appointment_id}.")
            return
        
        client_phone = appointment.client.phone
        if not client_phone:
            logger.warning(f"Номер телефона клиента для назначения {appointment_id} отсутствует.")
            return

        message = f"⏳ Напоминание: Через {hours_until} час{'а' if hours_until > 1 else ''} у вас запись!\n"
        message += f"💈 Услуга: {appointment.service.name}\n"
        message += f"🕑 Время: {appointment_time.strftime('%d.%m.%Y %H:%M')}\n"
        message += f"👨💼 Мастер: {appointment.master.name}\n"
        message += "Для подтверждения записи отправьте '1'\n"
        message += "Для отмены записи отправьте '2'"
        
        # Устанавливаем состояние ожидания подтверждения
        appointment.client.current_state = 'awaiting_confirmation'
        db.session.commit()

        send_message(client_phone, message)
        
        if hours_until == 1:
            # Если это напоминание за 1 час, запускаем задачу на отмену через 10 минут, если клиент не подтвердит
            cancel_time = datetime.now(local_tz) + timedelta(minutes=10)
            check_confirmation.apply_async(args=[appointment_id], eta=cancel_time)

    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания за {hours_until} часа: {str(e)}")


# В файле tasks.py
@celery.task(name='tasks.check_confirmation')
def check_confirmation(appointment_id):
    with current_app.app_context():
        try:
            appointment = Appointment.query.get(appointment_id)
            if not appointment:
                logger.warning(f"Запись {appointment_id} не найдена.")
                return

            if appointment.confirmation_status == 'pending':
                appointment.confirmation_status = 'expired'
                db.session.commit()
                send_message(
                    appointment.client.phone,
                    "⌛ Время подтверждения истекло. Запись автоматически отменена."
                )

                # Проверка наличия атрибута и его значения
                if hasattr(appointment, 'reminder_task_id') and appointment.reminder_task_id:
                    result = celery.AsyncResult(appointment.reminder_task_id)
                    if result.state != 'SUCCESS':
                        result.revoke(terminate=True)
                        logger.info(f"Задача {appointment.reminder_task_id} отменена.")
            else:
                logger.info(f"Статус записи {appointment_id} уже обновлен: {appointment.confirmation_status}")

        except Exception as e:
            logger.error(f"Ошибка в check_confirmation: {str(e)}", exc_info=True)
            db.session.rollback()

@celery.task(name='tasks.cleanup_old_appointments')
def cleanup_old_appointments():
    with current_app.app_context():
        try:
            month_ago = datetime.now() - timedelta(days=30)
            old_appointments = Appointment.query.filter(
                Appointment.date < month_ago
            ).all()
            
            for app in old_appointments:
                db.session.delete(app)
            
            db.session.commit()
            logger.info("Успешно удалены записи старше 30 дней.")
        except Exception as e:
            logger.error(f"Ошибка при очистке устаревших записей: {str(e)}")
            db.session.rollback()


