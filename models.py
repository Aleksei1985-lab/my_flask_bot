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

class Client(db.Model):
    __tablename__ = 'clients'
    
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    current_state = db.Column(db.String(50), nullable=False, default='active')
    next_week_start = db.Column(db.Integer, default=0)
    selected_service_id = db.Column(db.Integer, ForeignKey('services.id'))
    selected_date = db.Column(db.Date)
    selected_master_id = db.Column(db.Integer, db.ForeignKey('masters.id'))
    parent_service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=True)
    selected_service_category = Column(Integer)
    
    appointments = db.relationship('Appointment', back_populates='client')
    selected_service = db.relationship('Service', foreign_keys=[selected_service_id], backref='clients')
    parent_service = db.relationship('Service', foreign_keys=[parent_service_id], backref='clients_as_parent')  # Уточнение

    __table_args__ = (
        CheckConstraint('length(phone) >= 5', name='phone_length_check'),
    )

    @property
    def future_appointments(self):
        return Appointment.query.filter(
            Appointment.client_id == self.id,
            Appointment.date >= func.current_date(),
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).order_by(Appointment.date.asc()).all()

    def __repr__(self):
        return f'<Client {self.phone} {self.name}>'

    @classmethod
    def create_client(cls, phone, name, selected_service_id=None):
        """Создает нового клиента и сохраняет в БД."""
        if cls.query.filter_by(phone=phone).first():
            raise ValueError("Клиент с таким номером телефона уже существует")
        
        new_client = cls(
            phone=phone,
            name=name,
            selected_service_id=selected_service_id
        )
        db.session.add(new_client)
        db.session.commit()
        return new_client


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



class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(String(150), unique=True, nullable=False)
    email = db.Column(String(128), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(String(50), nullable=False, default='operator')
    is_active = db.Column(Boolean, default=True)
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    __table_args__ = (
        CheckConstraint(
            "role IN ('superuser', 'admin', 'manager', 'operator')", 
            name='role_check'
        ),
        CheckConstraint('length(username) >= 3', name='username_length_check'),
    )

    def __repr__(self):
        return f'<User {self.username} {self.role}>'