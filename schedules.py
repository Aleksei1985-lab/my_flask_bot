from datetime import date
from models import Schedule, Appointment

class ScheduleManager:
    @staticmethod
    def get_available_dates():
        today = date.today()
        available_dates = []
        # Установим диапазон дат
        for day in range(23, 32):  # Январь 23-31
            available_dates.append(date(today.year, 1, day))
        for day in range(1, 29):  # Февраль 1-28
            available_dates.append(date(today.year, 2, day))
        for day in range(1, 23):  # Март 1-22
            available_dates.append(date(today.year, 3, day))

        # Фильтруем доступные даты
        valid_dates = [
            single_date for single_date in available_dates
            if Schedule.query.filter_by(date=single_date, is_working_day=True).first()
        ]

        return valid_dates

    @staticmethod
    def get_available_times(selected_date):
        schedule = Schedule.query.filter_by(date=selected_date).first()
        if not schedule or not schedule.is_working_day:
            return []
        
        booked_appointments = Appointment.query.filter_by(date=selected_date).all()
        busy_times = {appointment.time.strftime('%H:%M') for appointment in booked_appointments}
        available_times = []

        # Логика определения доступного времени
        for hour in range(schedule.opening_time.hour, schedule.closing_time.hour):
            time_slot = f"{hour}:00-{hour}:45"
            if time_slot not in busy_times:
                available_times.append(time_slot)

        return available_times

