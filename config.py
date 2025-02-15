# config.py
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from celery import Celery

# Инициализация расширений
db = SQLAlchemy()
celery = Celery(__name__)  # Инициализация Celery глобально

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'mysecret')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///site.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "isolation_level": "SERIALIZABLE"
    }
    WTF_CSRF_ENABLED = True 
    apiUrl = "https://1103.api.green-api.com"
    idInstance = os.getenv('idInstance', "1103167173")
    apiTokenInstance = os.getenv('apiTokenInstance', "451181b283214ba5905a601b4ced8ae4df054c00a9194e7c8a")

    AUTH_HEADER = {
        'Authorization': f'Bearer {apiTokenInstance}'
    }

    broker_url = os.getenv('BROKER_URL', 'amqp://aleksei:1985@89.111.154.32:5672//')
    result_backend = os.getenv('RESULT_BACKEND', 'rpc://')

    @staticmethod
    def init_app(app):
        """Инициализация приложения с конфигурацией."""
        app.config.from_object(Config)

        
        # Обновление конфигурации Celery
        celery.conf.update(app.config)  
        celery.autodiscover_tasks(['tasks'])  # Автоматическое обнаружение задач

