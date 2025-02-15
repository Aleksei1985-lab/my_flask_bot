from app import create_app

app, celery = create_app()  # Создайте приложение и инициализируйте Celery

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
