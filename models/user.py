from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    user_type = db.Column(db.String(40), nullable=False, default="Student")
    monthly_income_preference = db.Column(db.Float, default=0)
    monthly_savings_target = db.Column(db.Float, default=0)
    financial_goal = db.Column(db.String(255), default="")
    currency = db.Column(db.String(10), default="INR")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    email_verified = db.Column(db.Boolean, nullable=False, default=True, index=True)
    otp_hash = db.Column(db.String(255), nullable=True)
    otp_expires_at = db.Column(db.DateTime, nullable=True)
    otp_attempts = db.Column(db.Integer, nullable=False, default=0)
    otp_created_at = db.Column(db.DateTime, nullable=True)
    otp_purpose = db.Column(db.String(30), nullable=True)
    auth_version = db.Column(db.Integer, nullable=False, default=0)

    incomes = db.relationship("Income", backref="user", lazy=True, cascade="all, delete-orphan")
    expenses = db.relationship("Expense", backref="user", lazy=True, cascade="all, delete-orphan")
    budgets = db.relationship("Budget", backref="user", lazy=True, cascade="all, delete-orphan")
    goals = db.relationship("Goal", backref="user", lazy=True, cascade="all, delete-orphan")
    reports = db.relationship("MonthlyReport", backref="user", lazy=True, cascade="all, delete-orphan")
    chat_messages = db.relationship("ChatMessage", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
