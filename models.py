from sqlalchemy import Integer, String, Date, Time, Boolean, ForeignKey, CheckConstraint, Table, Column, func
from sqlalchemy.orm import relationship, validates
from datetime import datetime, time, timedelta
from decimal import Decimal
from werkzeug.security import generate_password_hash, check_password_hash
from database import db
from flask_login import UserMixin

master_service_association = Table(
    'master_service_association', db.metadata,
    Column('master_id', Integer, ForeignKey('masters.id'), primary_key=True),
    Column('service_id', Integer, ForeignKey('services.id'), primary_key=True)
)

class Client(db.Model, UserMixin):
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)
    # Поля из clients
    phone = db.Column(String(20), unique=True, nullable=False)  # Обязательно для WhatsApp
    name = db.Column(String(100), nullable=False)              # Обязательно для всех
    current_state = db.Column(String(50), nullable=False, default='active')  # Для WhatsApp
    next_week_start = db.Column(Integer, default=0)            # Для WhatsApp
    selected_service_id = db.Column(Integer, ForeignKey('services.id'), nullable=True)  # Для WhatsApp
    selected_date = db.Column(Date, nullable=True)             # Для WhatsApp
    selected_master_id = db.Column(Integer, ForeignKey('masters.id'), nullable=True)  # Для WhatsApp
    parent_service_id = db.Column(Integer, ForeignKey('services.id'), nullable=True)  # Для WhatsApp
    selected_service_category = Column(Integer, nullable=True) # Для WhatsApp

    # Поля из users
    username = db.Column(String(150), unique=True, nullable=True)  # Для веб-версии
    email = db.Column(String(128), unique=True, nullable=True)     # Для веб-версии
    password_hash = db.Column(String(128), nullable=True)          # Для веб-версии
    role = db.Column(String(50), default='client')                 # Расширяем роли
    is_active = db.Column(Boolean, default=True)                   # Для веб-версии
    avatar_url = db.Column(db.String(255)) # ссылка на изображение

    # Связи
    appointments = db.relationship('Appointment', back_populates='client')
    selected_service = db.relationship('Service', foreign_keys=[selected_service_id], backref='clients_selected')
    parent_service = db.relationship('Service', foreign_keys=[parent_service_id], backref='clients_parent')
    selected_master = db.relationship('Master', foreign_keys=[selected_master_id], backref='clients_selected')

    __table_args__ = (
        CheckConstraint('length(phone) >= 5', name='phone_length_check'),
        CheckConstraint("role IN ('superuser', 'admin', 'manager', 'operator', 'client')", name='role_check'),
        CheckConstraint('length(username) >= 3 OR username IS NULL', name='username_length_check'),
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password) if self.password_hash else False

    @property
    def future_appointments(self):
        # Обновляем сессию перед запросом, чтобы избежать кэшированных данных
        db.session.expire_all()
        return Appointment.query.filter(
            Appointment.client_id == self.id,
            Appointment.date >= func.current_date(),
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).order_by(Appointment.date.asc(), Appointment.time.asc()).all()

    @classmethod
    def create_client(cls, phone, name, username=None, email=None, password=None, role='client', selected_service_id=None):
        """Создаёт нового клиента/пользователя."""
        if cls.query.filter_by(phone=phone).first():
            raise ValueError("Клиент с таким номером телефона уже существует")
        if username and cls.query.filter_by(username=username).first():
            raise ValueError("Пользователь с таким именем уже существует")
        if email and cls.query.filter_by(email=email).first():
            raise ValueError("Пользователь с таким email уже существует")

        new_client = cls(phone=phone, name=name, username=username, email=email, role=role, selected_service_id=selected_service_id)
        if password:
            new_client.set_password(password)
        db.session.add(new_client)
        db.session.commit()
        return new_client

    def __repr__(self):
        return f'<Client {self.phone} {self.name} {self.role}>'


class Appointment(db.Model):
    __tablename__ = 'appointments'
    
    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(db.Integer, nullable=False)  # Для оптимистичной блокировки
    __mapper_args__ = {
        "version_id_col": version_id
    }
    client_id = db.Column(Integer, ForeignKey('clients.id'), nullable=False, index=True)
    service_id = db.Column(Integer, ForeignKey('services.id'), nullable=False, index=True)
    master_id = db.Column(Integer, ForeignKey('masters.id'), nullable=False)
    date = db.Column(Date, nullable=False, index=True)
    time = db.Column(Time, nullable=False)
    status = db.Column(String(20), nullable=False, default='scheduled')
    confirmation_status = db.Column(db.String(20), default='pending')
    reminder_task_id = db.Column(db.String(255))  # Добавьте эту строку
    reminder_sent = db.Column(db.Boolean, default=False) 
    
    client = relationship('Client', back_populates='appointments')
    service = relationship('Service', back_populates='appointments')
    master = relationship('Master')

    __table_args__ = (
        CheckConstraint(
            "status IN ('scheduled', 'confirmed', 'completed', 'canceled')", 
            name="status_check"
        ),
    )
    @property
    def end_time(self):
        return (
            datetime.combine(self.date, self.time) + 
            timedelta(minutes=self.service.duration)
        ).time()
    
    @validates('date')
    def validate_date(self, key, date):
        if date < datetime.now().date():
            raise ValueError("Дата записи не может быть в прошлом")
        return date

    def __repr__(self):
        return f'<Appointment {self.date} {self.time}>'

class Service(db.Model):
    __tablename__ = 'services'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(String(150), unique=True, nullable=False, index=True)
    category = db.Column(String(100), nullable=False)
    parent_service_id = db.Column(Integer, ForeignKey('services.id'))  # Новое поле для иерархии
    description = db.Column(String(255))
    price = db.Column(db.Numeric(10, 2), nullable=False)
    duration = db.Column(Integer, nullable=False, default=30)
    masters = db.relationship('Master', 
                              secondary=master_service_association, 
                              back_populates='available_services')
    appointments = relationship('Appointment', back_populates='service')
    sub_services = relationship('Service', backref=db.backref('parent', remote_side=[id]))  # Иерархия услуг
    schedules = db.relationship('Schedule', back_populates='service')  # Здесь добавляем обратную связь

    __table_args__ = (
        CheckConstraint('price >= 0', name='non_negative_price'),
        CheckConstraint('duration >= 0', name='positive_duration'),
    )

    def __repr__(self):
        return f'<Service {self.name} {self.price}>'
    
class Master(db.Model):
    __tablename__ = 'masters'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(String(150), nullable=False)
    photo_url = db.Column(db.String(200))
    specializations = relationship('Specialization', back_populates='master', lazy='dynamic')
    available_services = db.relationship('Service', 
                                    secondary=master_service_association, 
                                    back_populates='masters')
    schedules = db.relationship('Schedule', back_populates='master')

    def __repr__(self):
        return f'<Master {self.name}>'

class Specialization(db.Model):
    __tablename__ = 'specializations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(String(100), nullable=False)
    master_id = db.Column(db.Integer, ForeignKey('masters.id'))

    master = relationship('Master', back_populates='specializations')

    def __repr__(self):
        return f'<Specialization {self.name}>'

class Schedule(db.Model):
    __tablename__ = 'schedules'
    
    # Поля модели
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    appointment_time = db.Column(db.Time, nullable=False)
    is_working_day = db.Column(db.Boolean, default=True)
    opening_time = db.Column(db.Time, nullable=False)
    closing_time = db.Column(db.Time, nullable=False)
    master_id = db.Column(db.Integer, db.ForeignKey('masters.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)

    # Отношения
    master = db.relationship('Master', back_populates='schedules')
    service = db.relationship('Service', back_populates='schedules')

    def __repr__(self):
        return f'<Schedule {self.date} {self.appointment_time} {self.master.name}>'

# Модель для рекламных баннеров
class Advertisement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    content = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    image_url = db.Column(db.String(255))

# Модель для расписания салона
class SalonSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day_of_week = db.Column(db.Integer)  # 0-6 (пн-вс)
    opening_time = db.Column(db.Time)
    closing_time = db.Column(db.Time)
    is_holiday = db.Column(db.Boolean, default=False)