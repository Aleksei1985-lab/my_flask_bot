from flask import current_app
from celery_app import celery
from datetime import datetime, timedelta
from celery import shared_task
from models import Appointment
from database import db
from routes import send_message, show_main_menu
import pytz
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import StaleDataError
import logging

logger = logging.getLogger(__name__)

def get_local_timezone():
    return pytz.timezone('Asia/Sakhalin')

@shared_task(name='tasks.send_24h_reminder', autoretry_for=(StaleDataError,), max_retries=3)
def send_24h_reminder(appointment_id):
    logger.info(f"[24h] Запуск задачи для записи {appointment_id}")
    with current_app.app_context():
        try:
            db.session.expire_all()
            appointment = Appointment.query.options(joinedload(Appointment.client)).get(appointment_id)
            if not appointment:
                logger.error(f"[24h] Запись {appointment_id} не найдена.")
                return

            if appointment.reminder_sent:
                logger.info(f"[24h] Напоминание для записи {appointment_id} уже отправлено.")
                return

            local_tz = get_local_timezone()
            appointment_time = local_tz.localize(datetime.combine(appointment.date, appointment.time))
            current_time = datetime.now(local_tz)

            if current_time >= appointment_time:
                logger.warning(f"[24h] Запись {appointment_id} уже неактуальна (время прошло).")
                return

            # Отправляем напоминание и устанавливаем состояние клиента
            _send_reminder(appointment_id, 24)

            # Планируем напоминание за 1 час только если запись не подтверждена
            if appointment.confirmation_status == 'pending':
                reminder_1h_time = appointment_time - timedelta(hours=1)
                utc_1h = reminder_1h_time.astimezone(pytz.utc)
                now_utc = datetime.now(pytz.utc)
                if utc_1h > now_utc:
                    task = send_1h_reminder.apply_async(
                        args=[appointment_id],
                        eta=utc_1h,
                        task_id=f"1h_reminder_{appointment_id}"
                    )
                    appointment.reminder_task_id = task.id
                    db.session.commit()
                    logger.info(f"[24h] 1h задача запланирована: {task.id}")
                else:
                    logger.warning(f"[24h] Время для 1h напоминания уже прошло для записи {appointment_id}")

        except StaleDataError as e:
            logger.error(f"StaleDataError: {str(e)}. Перезагружаем запись...")
            db.session.rollback()
            raise
        except Exception as e:
            logger.error(f"[24h] Ошибка: {str(e)}", exc_info=True)
            db.session.rollback()

@shared_task(name='tasks.send_1h_reminder')
def send_1h_reminder(appointment_id):
    logger.info(f"[1h] Запуск задачи для записи {appointment_id}")
    with current_app.app_context():
        try:
            appointment = Appointment.query.options(joinedload(Appointment.client)).get(appointment_id)
            if not appointment:
                logger.warning(f"[1h] Запись {appointment_id} не найдена, задача отменяется.")
                return

            if appointment.reminder_sent:
                logger.info(f"[1h] Напоминание для записи {appointment_id} уже отправлено.")
                return

            local_tz = get_local_timezone()
            appointment_time = local_tz.localize(datetime.combine(appointment.date, appointment.time))
            current_time = datetime.now(local_tz)

            if current_time >= appointment_time:
                logger.warning(f"[1h] Запись {appointment_id} уже неактуальна (время прошло).")
                return

            if appointment.confirmation_status == 'confirmed':
                logger.info(f"[1h] Запись {appointment_id} уже подтверждена, напоминание не отправляется.")
                return

            if appointment.confirmation_status != 'pending':
                logger.info(f"[1h] Запись {appointment_id} уже обработана ({appointment.confirmation_status}).")
                return

            _send_reminder(appointment_id, 1)

        except Exception as e:
            logger.error(f"[1h] Ошибка: {str(e)}", exc_info=True)

def _send_reminder(appointment_id, hours_until):
    try:
        appointment = Appointment.query.options(joinedload(Appointment.client)).get(appointment_id)
        if not appointment:
            logger.error(f"Запись {appointment_id} не найдена.")
            return

        if appointment.reminder_sent:
            logger.info(f"Напоминание для записи {appointment_id} уже отправлено.")
            return

        local_tz = get_local_timezone()
        appointment_time = local_tz.localize(datetime.combine(appointment.date, appointment.time))
        current_time = datetime.now(local_tz)

        if current_time >= appointment_time:
            logger.warning(f"Время для {hours_until}-часового напоминания прошло для записи {appointment_id}.")
            return

        user_phone = appointment.client.phone if appointment.client else None
        if not user_phone:
            logger.warning(f"Номер телефона клиента для назначения {appointment_id} отсутствует.")
            return

        message = f"⏳ Напоминание: Через {hours_until} час{'а' if hours_until > 1 else ''} у вас запись!\n"
        message += f"💈 Услуга: {appointment.service.name}\n"
        message += f"🕑 Время: {appointment_time.strftime('%d.%m.%Y %H:%M')}\n"
        message += f"👨💼 Мастер: {appointment.master.name}\n"
        if appointment.confirmation_status != 'confirmed':
            message += "Для подтверждения записи отправьте '1'\n"
            message += "Для отмены записи отправьте '2'"

        if appointment.confirmation_status != 'confirmed':
            appointment.client.current_state = 'awaiting_confirmation'
            db.session.commit()
            logger.debug(f"Состояние клиента {user_phone} установлено в awaiting_confirmation для записи {appointment_id}")

        send_message(user_phone, message)

        # Планируем check_confirmation для 1-часового напоминания
        if hours_until == 1 and appointment.confirmation_status == 'pending':
            cancel_time = current_time + timedelta(minutes=10)
            utc_cancel_time = cancel_time.astimezone(pytz.utc)
            now_utc = datetime.now(pytz.utc)
            if utc_cancel_time > now_utc:
                task = check_confirmation.apply_async(
                    args=[appointment_id],
                    eta=utc_cancel_time,
                    task_id=f"check_confirmation_{appointment_id}"
                )
                appointment.reminder_task_id = task.id
                db.session.commit()
                logger.info(f"[1h] check_confirmation запланирована для записи {appointment_id} на {utc_cancel_time.isoformat()} с task_id: {task.id}")
            else:
                logger.warning(f"[1h] Время для check_confirmation уже прошло для записи {appointment_id}")
        else:
            logger.debug(f"check_confirmation не запланирована: hours_until={hours_until}, status={appointment.confirmation_status}")

        appointment.reminder_sent = True
        db.session.commit()
        logger.info(f"Напоминание за {hours_until} часа отправлено для записи {appointment_id}")

    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания за {hours_until} часа: {str(e)}", exc_info=True)

@shared_task(name='tasks.check_confirmation')
def check_confirmation(appointment_id):
    with current_app.app_context():
        try:
            appointment = db.session.query(Appointment).options(joinedload(Appointment.client)).get(appointment_id)
            if not appointment:
                logger.warning(f"Запись {appointment_id} не найдена.")
                return

            if appointment.confirmation_status == 'pending':
                client = appointment.client
                client_phone = client.phone if client else None
                
                if appointment.reminder_task_id:
                    result = celery.AsyncResult(appointment.reminder_task_id)
                    if result.state not in ['SUCCESS', 'REVOKED']:
                        result.revoke(terminate=True)
                        logger.info(f"Задача напоминания {appointment.reminder_task_id} отозвана перед удалением.")
                
                db.session.delete(appointment)
                db.session.commit()
                
                if client_phone:
                    send_message(
                        client_phone,
                        "⌛ Время подтверждения истекло. Запись автоматически отменена."
                    )
                    client.current_state = 'active'
                    db.session.commit()
                    show_main_menu(client_phone)
                
                logger.info(f"Запись {appointment_id} удалена из-за отсутствия подтверждения.")
            else:
                logger.info(f"Запись {appointment_id} уже имеет статус: {appointment.confirmation_status}. Удаление не требуется.")

        except Exception as e:
            logger.error(f"Ошибка в check_confirmation: {str(e)}", exc_info=True)
            db.session.rollback()

@shared_task(name='tasks.cleanup_old_appointments')
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