from datetime import date, timedelta
from app import create_app
from extensions import db
from models import User, Income, Expense, Goal

app = create_app()
with app.app_context():
    user = User.query.filter_by(email="demo@example.com").first()
    if not user:
        user = User(name="Demo User", email="demo@example.com", user_type="Salaried Professional", monthly_savings_target=10000)
        user.set_password("DemoPass123!")
        db.session.add(user); db.session.flush()
        today = date.today()
        db.session.add_all([
            Income(user_id=user.id, amount=55000, source="Salary", date=today.replace(day=1), description="Monthly salary"),
            Expense(user_id=user.id, amount=16000, category="Rent", date=today - timedelta(days=5), description="Apartment rent", payment_method="Bank Transfer"),
            Expense(user_id=user.id, amount=6200, category="Food", date=today - timedelta(days=3), description="Groceries and meals", payment_method="UPI"),
            Expense(user_id=user.id, amount=3200, category="Transport", date=today - timedelta(days=7), description="Commute", payment_method="UPI"),
            Goal(user_id=user.id, name="Emergency buffer", target_amount=100000, current_amount=28000, target_date=today + timedelta(days=365), description="A calm cushion for unexpected months."),
        ])
        db.session.commit()
        print("Demo account created: demo@example.com / DemoPass123!")
    else:
        print("Demo account already exists.")
