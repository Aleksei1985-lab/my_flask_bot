# celery_app.py
from celery import Celery
from app import create_app  # Импортируйте create_app


def make_celery(app):
    celery = Celery(
        app.import_name,
        broker=app.config.get('broker_url'),  # Исправлено имя ключа
        backend=app.config.get('result_backend')  # Исправлено имя ключа
    )
    
        # Добавляем broker_connection_retry_on_startup и другие параметры
    celery.conf.broker_connection_retry_on_startup = True
    celery.conf.broker_connection_max_retries = None  # Можно установить по необходимости
    celery.conf.broker_connection_retry_interval = 5  # Интервал между попытками в секундах
    celery.conf.broker_transport_options = {
        'confirm_publish': True,
        'visibility_timeout': 82800,  # 1 час в секундах
    }
    celery.conf.task_acks_late = True

    celery.conf.update(app.config)
    celery.autodiscover_tasks(['my_flask_bot.tasks'])
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    return celery

app = create_app()  # Созданное приложение
celery = make_celery(app)  # Инициализация Celery
