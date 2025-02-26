# celery_app.py
from celery import Celery
from app import create_app  # Импортируйте create_app
from sqlalchemy.orm import scoped_session, sessionmaker
import os


def init_celery(app):
    # Инициализация Celery с именем вашего приложения
    celery = Celery(app.import_name)
    
    # Настройки брокера и бэкенда
    celery.conf.broker_url = app.config['broker_url']  # Используем нижний регистр
    celery.conf.result_backend = app.config['result_backend']  # Используем нижний регистр
    celery.conf.update(app.config)  # Обновление конфигурации
    celery.conf.update({
        # 'result_backend_transport_options': app.config['CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS'],
        # 'broker_transport_options': app.config['CELERY_BROKER_TRANSPORT_OPTIONS'],
        'task_serializer': 'json',
        'result_serializer': 'json',
        'accept_content': ['json'],
        'worker_max_tasks_per_child': 100,
        'broker_connection_retry_on_startup': True
    })
    

    celery.conf.task_acks_late = True
    print(f"CELERY_BROKER_URL: {os.getenv('CELERY_BROKER_URL')}")
    celery.conf.update(app.config)
    celery.autodiscover_tasks(['tasks'])
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    return celery



app = create_app()  # Созданное приложение
celery = init_celery(app)  # Инициализация Celery
