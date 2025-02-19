# app.py
from flask import Flask
from config import Config
from database import db
from flask_migrate import Migrate
from models import Schedule, User, Service, Master, Specialization
from flask_login import LoginManager
import logging



# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    Migrate(app, db)
    # from celery_app import make_celery
    app.config['broker_url'] = 'redis://:1985@89.111.154.32:6379/0'
    app.config['result_backend'] = 'redis://:1985@89.111.154.32:6379/0'
    # celery = make_celery(app)
    login_manager = LoginManager(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    with app.app_context():
        db.create_all()
        initialize_services()
        update_schedule()
    
        from routes import main_routes
        from admin_routes import admin_routes
        from auth_routes import auth_routes
        app.register_blueprint(main_routes)
        app.register_blueprint(admin_routes, url_prefix='/admin')
        app.register_blueprint(auth_routes, url_prefix='/auth')


    return app

def initialize_services():
    # Основные категории услуг
    main_services = [
        {"name": "Парикмахерские услуги", "category": "Основные", "price": 0, "duration": 0},
        {"name": "Косметические услуги", "category": "Основные", "price": 0, "duration": 0},
        {"name": "Ногтевой сервис", "category": "Основные", "price": 0, "duration": 0},
        {"name": "Массаж и SPA", "category": "Основные", "price": 0, "duration": 0},
        {"name": "Эпиляция", "category": "Основные", "price": 0, "duration": 0},
        {"name": "Визаж", "category": "Основные", "price": 0, "duration": 0}
    ]

    # Создаем мастеров
    masters = [
        {"name": "Иван Петров", "specializations": ["Мужская стрижка", "Бритье"]},
        {"name": "Ольга Сидорова", "specializations": ["Женская стрижка", "Окрашивание волос"]},
        {"name": "Анна Иванова", "specializations": ["Маникюр", "Педикюр", "Дизайн ногтей", "Вечерний макияж", "Свадебный макияж"]},
        {"name": "Мария Кузнецова", "specializations": ["Наращивание ресниц", "Коррекция бровей"]},
        {"name": "Александр Смирнов", "specializations": ["SPA-массаж", "Антицеллюлитный массаж"]},
        {"name": "Ирина Смирнова", "specializations": ["Мужская стрижка", "Антицеллюлитный массаж", "Чистка лица"]},
        {"name": "Елена Аксенова", "specializations": ["Чистка лица", "Пилинг", "Ароматерапия", "Восковая эпиляция", "Лазерная эпиляция"]}
    ]

    # Структура подуслуг
    services_structure = {
        "Парикмахерские услуги": [
            {"name": "Мужская стрижка", "price": 800, "duration": 45},
            {"name": "Женская стрижка", "price": 1500, "duration": 90},
            {"name": "Окрашивание волос", "price": 2500, "duration": 120},
            {"name": "Бритье", "price": 500, "duration": 30}
        ],
        "Косметические услуги": [
            {"name": "Чистка лица", "price": 2000, "duration": 60},
            {"name": "Пилинг", "price": 1800, "duration": 45},
            {"name": "Наращивание ресниц", "price": 3000, "duration": 120}
        ],
        "Ногтевой сервис": [
            {"name": "Маникюр", "price": 800, "duration": 60},
            {"name": "Педикюр", "price": 1200, "duration": 90},
            {"name": "Дизайн ногтей", "price": 500, "duration": 30}
        ],
        "Массаж и SPA": [
            {"name": "SPA-массаж", "price": 2500, "duration": 60},
            {"name": "Антицеллюлитный массаж", "price": 3000, "duration": 90},
            {"name": "Ароматерапия", "price": 1500, "duration": 45}
        ],
        "Эпиляция": [
            {"name": "Восковая эпиляция", "price": 1500, "duration": 30},
            {"name": "Лазерная эпиляция", "price": 5000, "duration": 60}
        ],
        "Визаж": [
            {"name": "Вечерний макияж", "price": 2000, "duration": 60},
            {"name": "Свадебный макияж", "price": 3500, "duration": 90}
        ]
    }

    try:
        # 1. Создаем основные категории услуг
        for service_data in main_services:
            existing = Service.query.filter_by(name=service_data['name']).first()
            if not existing:
                parent_service = Service(
                    name=service_data['name'],
                    category=service_data['category'],
                    price=service_data['price'],
                    duration=service_data['duration']
                )
                db.session.add(parent_service)
        db.session.commit()

        # 2. Добавляем подуслуги
        for parent_name, children in services_structure.items():
            parent = Service.query.filter_by(name=parent_name).first()
            if not parent:
                logger.error(f"Родительская услуга '{parent_name}' не найдена!")
                continue
            
            for service_data in children:
                existing = Service.query.filter_by(name=service_data['name']).first()
                if not existing:
                    new_service = Service(
                        name=service_data['name'],
                        category=parent.category,
                        price=service_data['price'],
                        duration=service_data['duration'],
                        parent_service_id=parent.id
                    )
                    db.session.add(new_service)
        db.session.commit()

        # 3. Добавляем мастеров и специализации
        for master_data in masters:
            master = Master.query.filter_by(name=master_data['name']).first()
            if not master:
                master = Master(name=master_data['name'])
                db.session.add(master)
                db.session.commit()
            
            for spec_name in master_data['specializations']:
                spec = Specialization.query.filter_by(name=spec_name, master_id=master.id).first()
                if not spec:
                    spec = Specialization(name=spec_name, master=master)
                    db.session.add(spec)
        db.session.commit()

        # 4. Привязываем мастеров к услугам
        associate_masters_with_services()

    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка инициализации услуг: {str(e)}")
        raise

    db.session.commit()  # Коммит после добавления всех подуслуг

def associate_masters_with_services():
    services = Service.query.all()  # Все услуги
    masters = Master.query.all()  # Все мастера

    for service in services:
        if service.parent_service_id:  # Только подуслуги
            for master in masters:
                # Проверяем, если специализация мастера соответствует подуслуге
                for spec in master.specializations:
                    if spec.name.strip().lower() == service.name.strip().lower():
                        if master not in service.masters:
                            service.masters.append(master)
                            logger.info(f"Мастер {master.name} добавлен к подуслуге '{service.name}'")
                            logger.info("Проверка привязки мастеров к подуслугам:")
                            for service in Service.query.all():
                                if service.parent_service_id:  # Только подуслуги
                                    logger.info(f"Подуслуга: {service.name}, мастера: {[m.name for m in service.masters]}")

    db.session.commit()

def update_schedule():
    from datetime import datetime, timedelta, time
    today = datetime.now().date()
    masters = Master.query.all()

    schedules_dict = {}
    all_schedules = Schedule.query.filter(Schedule.date.between(today, today + timedelta(days=30))).all()
    for schedule in all_schedules:
        key = (schedule.date, schedule.master_id, schedule.service_id)
        schedules_dict[key] = schedule

    for master in masters:
        services = [s for s in master.available_services if s.parent_service_id]

        if not services:
            logger.warning(f"У мастера {master.name} нет доступных подуслуг!")
            continue

        for i in range(30):  # Генерация расписания на 30 дней вперед
            future_date = today + timedelta(days=i)

            for service in services:
                key = (future_date, master.id, service.id)
                
                if key not in schedules_dict:  # Проверка существующего расписания
                    # Установите временные параметры
                    opening_time = time(9, 0)
                    closing_time = time(22, 0)
                    duration = service.duration

                    current_start_time = opening_time
                    while current_start_time < closing_time:
                        new_schedule = Schedule(
                            date=future_date,
                            appointment_time=current_start_time,
                            is_working_day=True,
                            opening_time=opening_time,
                            closing_time=closing_time,
                            master_id=master.id,
                            service_id=service.id
                        )
                        db.session.add(new_schedule)
                        current_start_time = (datetime.combine(datetime.today(), current_start_time) + 
                                            timedelta(minutes=service.duration)).time()

    db.session.commit()


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
