from flask import Blueprint, render_template, redirect, url_for, request, flash
from models import User
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from database import db
from flask_wtf import csrf
auth_routes = Blueprint('auth', __name__)

@auth_routes.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        # Исправленная проверка пароля
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('admin.manage_appointments'))
        
        flash("Неверные учетные данные", "danger")
    return render_template('login.html')

@auth_routes.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Выход выполнен", "success")
    return redirect(url_for('auth.login'))
