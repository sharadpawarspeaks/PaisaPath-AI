from datetime import date, datetime

from extensions import db


class Income(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    source = db.Column(db.String(40), nullable=False)
    frequency = db.Column(db.String(20), nullable=False, default="Monthly")
    recurring = db.Column(db.Boolean, nullable=False, default=True)
    end_date = db.Column(db.Date, nullable=True)
    annual_increase_percent = db.Column(db.Float, nullable=False, default=0)
    annual_increase_effective_date = db.Column(db.Date, nullable=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    description = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(40), nullable=False)
    frequency = db.Column(db.String(20), nullable=False, default="Monthly")
    recurring = db.Column(db.Boolean, nullable=False, default=True)
    end_date = db.Column(db.Date, nullable=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    description = db.Column(db.String(255), default="")
    payment_method = db.Column(db.String(40), default="UPI")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    category = db.Column(db.String(40), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    source = db.Column(db.String(20), default="manual")


class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    current_amount = db.Column(db.Float, nullable=False, default=0)
    target_date = db.Column(db.Date, nullable=True)
    description = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def progress(self):
        return min(100, round((self.current_amount / self.target_amount) * 100, 1)) if self.target_amount else 0

    @property
    def remaining(self):
        return max(0, self.target_amount - self.current_amount)

    @property
    def is_achieved(self):
        return self.remaining <= 0

    @property
    def days_remaining(self):
        if not self.target_date:
            return None
        return (self.target_date - date.today()).days

    @property
    def months_remaining(self):
        if not self.target_date:
            return None
        today = date.today()
        days = (self.target_date - today).days
        if days <= 0:
            return 0
        cal_months = (self.target_date.year - today.year) * 12 + (self.target_date.month - today.month)
        return max(1, cal_months)

    @property
    def monthly_savings_needed(self):
        rem = self.remaining
        if rem <= 0:
            return 0.0
        if not self.target_date:
            return rem
        today = date.today()
        days = (self.target_date - today).days
        if days <= 0:
            return rem
        cal_months = (self.target_date.year - today.year) * 12 + (self.target_date.month - today.month)
        months = max(1, cal_months)
        return round(rem / months, 2)


class MonthlyReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
