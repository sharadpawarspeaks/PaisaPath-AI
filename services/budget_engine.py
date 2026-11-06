from collections import defaultdict
from models import Expense
from services.financial_engine import monthly_metrics
from sqlalchemy import extract

CATEGORIES = ["Rent", "Food", "Transport", "Education", "Healthcare", "Utilities", "Shopping", "Entertainment", "Subscriptions", "Household", "Other"]
ESSENTIALS = {"Rent", "Food", "Transport", "Education", "Healthcare", "Utilities", "Household"}

def recommended_budget(user, month, year):
    metrics = monthly_metrics(user.id, month, year)
    income = metrics["total_income"] or user.monthly_income_preference or 0
    history = defaultdict(float)
    expenses = Expense.query.filter_by(user_id=user.id).filter(extract("year", Expense.date) == year).all()
    for expense in expenses:
        history[expense.category] += expense.amount
    if history:
        total_history = sum(history.values()) or 1
        allocations = {category: income * history.get(category, 0) / total_history for category in CATEGORIES if history.get(category)}
        allocations["Savings"] = max(user.monthly_savings_target or income * 0.2, 0)
    else:
        weights = {"Rent": .25, "Food": .12, "Transport": .08, "Education": .08, "Healthcare": .05, "Utilities": .08, "Household": .07, "Shopping": .06, "Entertainment": .05, "Other": .06}
        allocations = {category: round(income * weight, 2) for category, weight in weights.items()}
        allocations["Savings"] = round(max(user.monthly_savings_target, income * .2), 2)
    return {category: round(amount, 2) for category, amount in allocations.items() if amount > 0}
