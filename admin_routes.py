from flask import Blueprint, request, render_template, redirect, url_for, flash
from flask_login import login_required, current_user, logout_user
from database import db
from models import Appointment, Service, User, Client
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

admin_routes = Blueprint('admin', __name__)

@admin_routes.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Вы успешно вышли из системы.", "success")
    return redirect(url_for('auth.login'))

@admin_routes.route('/manage_appointments', methods=['GET'])
@login_required
def manage_appointments():
    try:
        # Получаем записи с полной информацией
        appointments = db.session.query(Appointment).options(
            joinedload(Appointment.client),
            joinedload(Appointment.service)
        ).order_by(Appointment.date.desc()).all()
        
        return render_template('manage_appointments.html', 
                             appointments=appointments)
    except Exception as e:
        logger.error(f"Ошибка загрузки записей: {str(e)}")
        flash("Произошла ошибка при загрузке данных", "danger")
        return redirect(url_for('admin.manage_appointments'))
    
@admin_routes.route('/delete_appointment/<int:appointment_id>', methods=['POST'])
@login_required
def delete_appointment(appointment_id):
    try:
        appointment = Appointment.query.get(appointment_id)
        if appointment:
            db.session.delete(appointment)
            db.session.commit()
            flash("Запись успешно удалена", "success")
        else:
            flash("Запись не найдена", "warning")
    except Exception as e:
        logger.error(f"Ошибка удаления записи: {e}")
        flash("Ошибка при удалении записи", "error")
    return redirect(url_for('admin.manage_appointments'))

@admin_routes.route('/create_appointment', methods=['GET', 'POST'])
@login_required
def create_appointment():
    try:
        # Получаем данные формы
        client_id = request.form.get('client_id')
        service_id = request.form.get('service_id')
        date_str = request.form.get('date')
        time_str = request.form.get('time')

        # Валидация данных
        if not all([client_id, service_id, date_str, time_str]):
            flash("Заполните все обязательные поля", "warning")
            return redirect(url_for('admin.create_appointment'))

        # Преобразование даты и времени
        start_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        service = Service.query.get(service_id)
        end_time = start_time + timedelta(minutes=service.duration)

        # Проверка временных конфликтов
        conflict = Appointment.query.filter(
            Appointment.date == start_time.date(),
            (
                (Appointment.time <= start_time.time()) & 
                (Appointment.time + (Service.duration * 60) > start_time.time())
            ) | (
                (Appointment.time >= start_time.time()) & 
                (Appointment.time < end_time.time())
            )
        ).first()

        if conflict:
            flash("Выбранное время пересекается с существующей записью", "danger")
            return redirect(url_for('admin.create_appointment'))

        # Создание новой записи
        new_appointment = Appointment(
            client_id=client_id,
            service_id=service_id,
            date=start_time.date(),
            time=start_time.time(),
            status='scheduled'
        )

        db.session.add(new_appointment)
        db.session.commit()
        flash("Запись успешно создана", "success")

    except ValueError as e:
        logger.error(f"Ошибка формата данных: {str(e)}")
        flash("Некорректный формат даты или времени", "danger")
    except Exception as e:
        logger.error(f"Ошибка создания записи: {str(e)}")
        flash("Произошла ошибка при создании записи", "danger")
    
    return redirect(url_for('admin.manage_appointments'))

@admin_routes.route('/manage_users', methods=['GET'])
@login_required
def manage_users():
    if current_user.role != 'superuser':
        flash("У вас нет прав доступа для этой операции.", "error")
        return redirect(url_for('admin.manage_appointments'))
    
    users = User.query.all()
    return render_template('manage_users.html', users=users)

@admin_routes.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if current_user.role != 'superuser':
        flash("У вас нет прав доступа для этой операции.", "error")
        return redirect(url_for('admin.manage_users'))

    user = User.query.filter_by(id=user_id).first()  # Используем filter_by
    if not user:
        flash("Пользователь не найден", "error")
        return redirect(url_for('admin.manage_users'))

    if request.method == 'POST':
        username = request.form.get('username')
        role = request.form.get('role')

        if username and role:
            try:
                user.username = username
                user.role = role
                db.session.commit()
                flash("Изменения успешно сохранены", "success")
            except Exception as e:
                logger.error(f"Ошибка при обновлении пользователя: {e}")
                flash("Ошибка при обновлении пользователя", "error")
        else:
            flash("Заполните все поля", "warning")
        return redirect(url_for('admin.manage_users'))

    return render_template('edit_user.html', user=user)

@admin_routes.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.role != 'superuser':
        flash("У вас нет прав доступа для этой операции.", "error")
        return redirect(url_for('admin.manage_users'))

    try:
        user = User.query.get(user_id)
        if user:
            db.session.delete(user)
            db.session.commit()
            flash("Пользователь успешно удален", "success")
        else:
            flash("Пользователь не найден", "warning")
    except Exception as e:
        logger.error(f"Ошибка при удалении пользователя: {e}")
        flash("Ошибка при удалении пользователя", "error")
    
    return redirect(url_for('admin.manage_users'))

@admin_routes.route('/edit_appointment/<int:appointment_id>', methods=['GET', 'POST'])
@login_required
def edit_appointment(appointment_id):
    if current_user.role != 'superuser':
        flash("У вас нет прав доступа для этой операции.", "error")
        return redirect(url_for('admin.manage_appointments'))

    appointment = Appointment.query.get(appointment_id)
    clients = Client.query.all()

    if not appointment:
        flash("Запись не найдена.", "error")
        return redirect(url_for('admin.manage_appointments'))

    if request.method == 'POST':
        client_id = request.form.get('client_id')
        date = request.form.get('date')
        time = request.form.get('time')

        try:
            date_time = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            appointment.client_id = client_id
            appointment.date = date_time.date()
            appointment.time = date_time.time()
            db.session.commit()
            flash("Запись успешно обновлена", "success")
            return redirect(url_for('admin.manage_appointments'))
        except Exception as e:
            logger.error(f"Ошибка редактирования записи: {e}")
            flash("Ошибка при редактировании записи", "error")

    return render_template('edit_appointment.html', appointment=appointment, clients=clients)

@admin_routes.route('/manage_services', methods=['GET', 'POST'])
@login_required
def manage_services():
    services = Service.query.all()
    if request.method == 'POST':
        service_name = request.form.get('name')
        service_price = request.form.get('price')
        service_duration = request.form.get('duration')

        if service_name and service_price and service_duration:
            try:
                price = float(service_price)
                duration = int(service_duration)
                new_service = Service(
                    name=service_name,
                    price=price,
                    duration=duration
                )
                db.session.add(new_service)
                db.session.commit()
                flash("Услуга добавлена", "success")
            except ValueError:
                flash("Введите корректные числовые значения", "error")
            except Exception as e:
                logger.error(f"Ошибка при добавлении услуги: {e}")
                flash("Ошибка при добавлении услуги", "error")
        else:
            flash("Все поля должны быть заполнены", "warning")
        return redirect(url_for('admin.manage_services'))

    return render_template('manage_services.html', services=services)


@admin_routes.route('/delete_service/<int:service_id>', methods=['POST'])
@login_required
def delete_service(service_id):
    try:
        service = Service.query.get(service_id)
        if service:
            db.session.delete(service)
            db.session.commit()
            flash("Услуга успешно удалена", "success")
        else:
            flash("Услуга не найдена", "warning")
    except Exception as e:
        logger.error(f"Ошибка при удалении услуги: {e}")
        flash("Ошибка при удалении услуги", "error")
    return redirect(url_for('admin.manage_services'))

@admin_routes.route('/edit_service/<int:service_id>', methods=['GET', 'POST'])
@login_required
def edit_service(service_id):
    service = Service.query.get(service_id)
    if not service:
        flash("Услуга не найдена", "error")
        return redirect(url_for('admin.manage_services'))

    if request.method == 'POST':
        service.name = request.form.get('name')
        service.price = float(request.form.get('price'))
        service.duration = int(request.form.get('duration'))
        
        try:
            db.session.commit()
            flash("Услуга успешно обновлена", "success")
            return redirect(url_for('admin.manage_services'))
        except Exception as e:
            logger.error(f"Ошибка обновления услуги: {e}")
            flash("Ошибка при обновлении услуги", "error")

    return render_template('edit_service.html', service=service)

@admin_routes.route('/create_client', methods=['GET', 'POST'])
@login_required
def create_client():
    if current_user.role != 'superuser':
        flash("У вас нет прав доступа для этой операции.", "error")
        return redirect(url_for('admin.manage_appointments'))

    if request.method == 'POST':
        data = request.get_json()
        name = data.get('name')
        phone = data.get('phone')

        if not name or not phone:
            return {"success": False, "message": "Все поля должны быть заполнены"}, 400

        existing_client = Client.query.filter_by(phone=phone).first()
        if existing_client:
            return {"success": False, "message": "Клиент с таким номером телефона уже существует"}, 400
    
        new_client = Client(name=name, phone=phone)
        db.session.add(new_client)
        db.session.commit()
        return {"success": True}, 200

@admin_routes.route('/create_user', methods=['GET', 'POST'])
@login_required
def create_user():
    if current_user.role != 'superuser':
        flash("У вас нет прав доступа для этой операции.", "error")
        return redirect(url_for('admin.manage_services'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')

        if username and password and role:
            try:
                existing_user = User.query.filter_by(username=username).first()
                if existing_user:
                    flash("Пользователь с таким именем уже существует", "warning")
                    return redirect(url_for('admin.create_user'))

                hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
                new_user = User(username=username, password=hashed_password, role=role)
                db.session.add(new_user)
                db.session.commit()
                flash("Пользователь успешно создан", "success")
            except Exception as e:
                logger.error(f"Ошибка при создании пользователя: {e}")
                flash("Ошибка при создании пользователя", "error")
        else:
            flash("Заполните все поля", "warning")
        return redirect(url_for('admin.create_user'))

    return render_template('create_user.html')