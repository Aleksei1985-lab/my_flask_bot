# web_routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from models import Client, Appointment, Service, Master
from app import db
from forms import LoginForm, RegistrationForm, UpdateProfileForm, BookingForm
from datetime import datetime

web_bp = Blueprint('web', __name__)

# Главная страница с рекламным баннером и списком услуг
@web_bp.route('/')
def index():
    services = Service.query.filter(Service.parent_service_id.is_(None)).all()
    masters = Master.query.all()
    return render_template('index.html', services=services, masters=masters)

# Страница входа
@web_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        # Например, ищем клиента по email (или по номеру телефона)
        client = Client.query.filter_by(email=form.email.data).first()
        if client and client.check_password(form.password.data):
            login_user(client)
            flash('Добро пожаловать!', 'success')
            return redirect(url_for('web.dashboard'))
        else:
            flash('Неверные учетные данные', 'danger')
    return render_template('web.login.html', form=form)

# Страница регистрации
@web_bp.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            client = Client.create_client(
                phone=form.phone.data,
                name=form.username.data,
                username=form.username.data,
                email=form.email.data,
                password=form.password.data,
                role='client'
            )
            login_user(client)
            flash('Регистрация прошла успешно!', 'success')
            return redirect(url_for('web.dashboard'))
        except ValueError as e:
            flash(str(e), 'danger')
    return render_template('web.register.html', form=form)

# Личный кабинет
@web_bp.route('/dashboard')
@login_required
def dashboard():
    # Получаем записи клиента
    appointments = current_user.future_appointments
    return render_template('dashboard.html', appointments=appointments)

# Редактирование профиля
@web_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = UpdateProfileForm(obj=current_user)
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.email = form.email.data
        current_user.phone = form.phone.data
        # Если требуется, обновляем и аватар
        current_user.avatar_url = form.avatar_url.data
        # Обновляем пароль, если введено новое значение
        if form.password.data:
            current_user.set_password(form.password.data)
        db.session.commit()
        flash('Профиль обновлен!', 'success')
        return redirect(url_for('web.profile'))
    return render_template('profile.html', form=form)

# Запись на услугу
@web_bp.route('/book/<int:service_id>', methods=['GET', 'POST'])
@login_required
def book_service(service_id):
    service = Service.query.get_or_404(service_id)
    masters = service.masters
    form = BookingForm()
    # Обновляем список мастеров для выбора в форме
    form.master.choices = [(m.id, m.name) for m in masters]
    
    if form.validate_on_submit():
        appointment = Appointment(
            client_id=current_user.id,
            service_id=service.id,
            master_id=form.master.data,
            date=form.date.data,
            time=form.time.data,
            status='scheduled',
            confirmation_status='pending'
        )
        db.session.add(appointment)
        db.session.commit()
        flash('Вы успешно записались!', 'success')
        return redirect(url_for('web.dashboard'))
    
    return render_template('book_service.html', service=service, form=form)

# Отмена записи
@web_bp.route('/cancel/<int:appointment_id>')
@login_required
def cancel_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    if appointment.client_id != current_user.id:
        flash('У вас нет прав отменить эту запись', 'danger')
        return redirect(url_for('web.dashboard'))
    db.session.delete(appointment)
    db.session.commit()
    flash('Запись отменена', 'success')
    return redirect(url_for('web.dashboard'))

@web_bp.route('/advertise', methods=['GET', 'POST'])
def advertise():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        message = request.form.get('message')
        # Здесь можно добавить логику для обработки данных (например, сохранение в базу данных)
        flash('Ваша заявка на рекламу успешно отправлена!', 'success')
        return redirect(url_for('web.advertise'))
    return render_template('advertise.html')

@web_bp.route('/masters')
def masters():
    masters = Master.query.all()
    return render_template('masters.html', masters=masters)
