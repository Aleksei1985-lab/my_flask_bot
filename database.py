# database.py
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import scoped_session, sessionmaker

db = SQLAlchemy()
Session = scoped_session(sessionmaker())