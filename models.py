from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(100), unique=True, nullable=False)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    faculty = db.Column(db.String(100))
    course = db.Column(db.String(50))
    points = db.Column(db.Integer, default=450)
    helps_done = db.Column(db.Integer, default=0)
    is_admin = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    ban_reason = db.Column(db.String(500), nullable=True)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(50), nullable=False)
    text = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    author_name = db.Column(db.String(100))
    helper_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    pts = db.Column(db.Integer, default=50)
    is_urgent = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='open')
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.String(100), nullable=False)
    text = db.Column(db.Text)
    author_name = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class MerchOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    item_name = db.Column(db.String(100))
    code = db.Column(db.String(20), unique=True)
    status = db.Column(db.String(20), default='pending')
    date_created = db.Column(db.DateTime, default=datetime.utcnow)