# admin_routes.py
from flask import Blueprint, render_template, redirect, url_for
from models import Master, Service
from app import db

admin_routes = Blueprint('admin', __name__)

@admin_routes.route('/services')
def manage_services():
    services = Service.query.all()
    return render_template('admin/manage_services.html', services=services)

@admin_routes.route('/masters')
def manage_masters():
    masters = Master.query.all()
    return render_template('admin/manage_masters.html', masters=masters)
