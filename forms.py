from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, DateField
from wtforms.validators import DataRequired, Email, EqualTo

class RegistrationForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired()])
    email = StringField('Электронная почта', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired(), EqualTo('confirm', message='Пароли должны совпадать')])
    confirm = PasswordField('Подтвердите пароль')
    submit = SubmitField('Регистрация')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class UpdateProfileForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone', validators=[DataRequired()])
    avatar_url = StringField('Avatar URL')
    password = PasswordField('New Password')
    submit = SubmitField('Update Profile')


class BookingForm(FlaskForm):
    customer_name = StringField('Имя клиента', validators=[DataRequired()])
    service_date = DateField('Дата услуги', validators=[DataRequired()])
    service_type = StringField('Тип услуги', validators=[DataRequired()])
    submit = SubmitField('Забронировать')