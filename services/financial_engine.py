from collections import defaultdict
from calendar import monthrange
from datetime import date, timedelta
from sqlalchemy import extract
from models import Income, Expense, Budget, Goal
from services.finance_calculator import calculate_goal


def month_bounds(year, month):
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def calculate_metrics(incomes, expenses, budgets=None):
    total_income = round(sum(item.amount for item in incomes), 2)
    total_expenses = round(sum(item.amount for item in expenses), 2)
    savings = round(total_income - total_expenses, 2)
    categories = defaultdict(float)
    for expense in expenses:
        categories[expense.category] += expense.amount
    category_expenses = {key: round(value, 2) for key, value in sorted(categories.items(), key=lambda pair: -pair[1])}
    budget_total = round(sum(item.amount for item in (budgets or [])), 2)
    remaining_budget = round(budget_total - total_expenses, 2)
    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "total_savings": savings,
        "savings_rate": round((savings / total_income) * 100, 2) if total_income else 0,
        "category_expenses": category_expenses,
        "budget_total": budget_total,
        "budget_utilization": round((total_expenses / budget_total) * 100, 2) if budget_total else 0,
        "remaining_budget": remaining_budget,
        "overspending": max(0, round(total_expenses - budget_total, 2)) if budget_total else 0,
        "highest_category": next(iter(category_expenses), "None"),
    }


def health_label(metrics):
    if metrics["total_income"] <= 0:
        return "Needs Attention"
    if metrics["savings_rate"] >= 20 and metrics["budget_utilization"] <= 90:
        return "Healthy"
    return "Review Spending"


def monthly_metrics(user_id, month=None, year=None):
    today = date.today()
    month = month or today.month
    year = year or today.year
    incomes = Income.query.filter_by(user_id=user_id).filter(extract("month", Income.date) == month, extract("year", Income.date) == year).all()
    expenses = Expense.query.filter_by(user_id=user_id).filter(extract("month", Expense.date) == month, extract("year", Expense.date) == year).all()
    budgets = Budget.query.filter_by(user_id=user_id, month=month, year=year).all()
    metrics = calculate_metrics(incomes, expenses, budgets)
    metrics["month"] = month
    metrics["year"] = year
    metrics["budget_map"] = {item.category: item.amount for item in budgets}
    metrics["overspending"] = {category: round(amount - metrics["budget_map"][category], 2) for category, amount in metrics["category_expenses"].items() if category in metrics["budget_map"] and amount > metrics["budget_map"][category]}
    return metrics


def trend_metrics(user_id, months=6):
    today = date.today()
    trends = []
    for offset in range(months - 1, -1, -1):
        month_index = today.month - offset
        year = today.year + (month_index - 1) // 12
        month = (month_index - 1) % 12 + 1
        metrics = monthly_metrics(user_id, month, year)
        trends.append({"label": f"{year}-{month:02d}", "income": metrics["total_income"], "expenses": metrics["total_expenses"], "savings": metrics["total_savings"]})
    return trends


def _month_shift(year, month, offset):
    index = year * 12 + month - 1 + offset
    return index // 12, index % 12 + 1


def analytics_period(preset="this_month", start_date=None, end_date=None, as_of=None):
    """Resolve the report period without putting date arithmetic in templates."""
    current = as_of or date.today()
    if preset == "custom" and start_date and end_date and start_date <= end_date:
        return start_date, end_date
    if preset == "last_month":
        year, month = _month_shift(current.year, current.month, -1)
        return month_bounds(year, month)
    if preset in {"last_3_months", "last_6_months"}:
        count = 3 if preset == "last_3_months" else 6
        year, month = _month_shift(current.year, current.month, -(count - 1))
        return month_bounds(year, month)[0], month_bounds(current.year, current.month)[1]
    if preset == "this_year":
        return date(current.year, 1, 1), date(current.year, 12, 31)
    return month_bounds(current.year, current.month)


def _period_metrics(user_id, start_date, end_date):
    incomes = Income.query.filter_by(user_id=user_id).filter(Income.date >= start_date, Income.date <= end_date).all()
    expenses = Expense.query.filter_by(user_id=user_id).filter(Expense.date >= start_date, Expense.date <= end_date).all()
    budgets = Budget.query.filter_by(user_id=user_id).filter(
        Budget.year * 100 + Budget.month >= start_date.year * 100 + start_date.month,
        Budget.year * 100 + Budget.month <= end_date.year * 100 + end_date.month,
    ).all()
    metrics = calculate_metrics(incomes, expenses, budgets)
    metrics["budget_map"] = {}
    for budget in budgets:
        metrics["budget_map"][budget.category] = round(metrics["budget_map"].get(budget.category, 0) + budget.amount, 2)
    metrics["overspending"] = {
        category: round(amount - metrics["budget_map"][category], 2)
        for category, amount in metrics["category_expenses"].items()
        if category in metrics["budget_map"] and amount > metrics["budget_map"][category]
    }
    return metrics, incomes, expenses, budgets


def _previous_period(start_date, end_date):
    days = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    return previous_end - timedelta(days=days - 1), previous_end


def analytics_report(user_id, preset="this_month", start_date=None, end_date=None, as_of=None):
    """Return all Financial Report analytics from the central calculation engine."""
    period_start, period_end = analytics_period(preset, start_date, end_date, as_of)
    metrics, incomes, expenses, budgets = _period_metrics(user_id, period_start, period_end)
    previous_start, previous_end = _previous_period(period_start, period_end)
    previous, _, _, _ = _period_metrics(user_id, previous_start, previous_end)

    trend = []
    cursor_year, cursor_month = period_start.year, period_start.month
    while (cursor_year, cursor_month) <= (period_end.year, period_end.month):
        month_start, month_end = month_bounds(cursor_year, cursor_month)
        month_metrics, _, _, _ = _period_metrics(user_id, month_start, month_end)
        trend.append({
            "label": f"{cursor_year}-{cursor_month:02d}",
            "income": month_metrics["total_income"],
            "expenses": month_metrics["total_expenses"],
            "savings": month_metrics["total_savings"],
        })
        cursor_year, cursor_month = _month_shift(cursor_year, cursor_month, 1)

    budget_map = {}
    for budget in budgets:
        budget_map[budget.category] = round(budget_map.get(budget.category, 0) + budget.amount, 2)
    categories = sorted(set(metrics["category_expenses"]) | set(budget_map), key=lambda category: -metrics["category_expenses"].get(category, 0))
    budget_vs_actual = [{
        "category": category,
        "budget": budget_map.get(category, 0),
        "actual": metrics["category_expenses"].get(category, 0),
        "variance": round(metrics["category_expenses"].get(category, 0) - budget_map.get(category, 0), 2),
        "over": max(0, round(metrics["category_expenses"].get(category, 0) - budget_map.get(category, 0), 2)),
    } for category in categories]
    category_breakdown = [{
        "category": category,
        "amount": amount,
        "percentage": round((amount / metrics["total_expenses"]) * 100, 2) if metrics["total_expenses"] else 0,
    } for category, amount in metrics["category_expenses"].items()]

    all_incomes = Income.query.filter_by(user_id=user_id).all()
    all_expenses = Expense.query.filter_by(user_id=user_id).all()
    goals = Goal.query.filter_by(user_id=user_id).order_by(Goal.target_date.asc().nullslast(), Goal.created_at.desc()).all()
    goal_calculations = [calculate_goal(goal, all_incomes, expenses=all_expenses, as_of=as_of) for goal in goals]
    active_goals = [calculation for calculation in goal_calculations if calculation["remaining_amount"] > 0]
    total_required = round(sum(calculation["monthly_required"] for calculation in active_goals), 2)
    available_capacity = round(max(0, metrics["total_income"] - metrics["total_expenses"]), 2)
    top_expense = next(iter(metrics["category_expenses"].items()), None)

    def change(current, prior):
        return round(((current - prior) / abs(prior)) * 100, 2) if prior else None

    alerts = []
    for item in budget_vs_actual:
        if item["over"] > 0:
            alerts.append({"kind": "Budget exceeded", "message": f'{item["category"]} spending is ₹{item["over"]:,.0f} above its budget.'})
    for calculation in active_goals:
        if calculation["savings_shortfall"] > 0:
            alerts.append({"kind": "Goal pace", "message": f'{calculation["goal_name"]} needs ₹{calculation["savings_shortfall"]:,.0f} more per month at the current pace.'})
    if previous["total_expenses"] and metrics["total_expenses"] > previous["total_expenses"]:
        alerts.append({"kind": "Expense increase", "message": f'Expenses increased from ₹{previous["total_expenses"]:,.0f} to ₹{metrics["total_expenses"]:,.0f}.'})
    if metrics["total_savings"] > previous["total_savings"]:
        alerts.append({"kind": "Savings increase", "message": f'Savings increased from ₹{previous["total_savings"]:,.0f} to ₹{metrics["total_savings"]:,.0f}.'})

    insights = []
    if metrics["total_income"] or metrics["total_expenses"]:
        insights.append(f'Savings rate is {metrics["savings_rate"]:.1f}%.')
    if top_expense:
        insights.append(f'{top_expense[0]} is your largest expense at ₹{top_expense[1]:,.0f}.')
    if any(item["over"] > 0 for item in budget_vs_actual):
        over_budget = max(budget_vs_actual, key=lambda item: item["over"])
        insights.append(f'{over_budget["category"]} is ₹{over_budget["over"]:,.0f} above its budget.')
    if active_goals:
        insights.append(f'You have {len(active_goals)} active financial goal{"s" if len(active_goals) != 1 else ""}.')
    if available_capacity > 0:
        insights.append(f'Current monthly savings capacity is ₹{available_capacity:,.0f}.')

    metrics["period_start"] = period_start
    metrics["period_end"] = period_end
    metrics["budget_vs_actual"] = budget_vs_actual
    metrics["top_expense"] = top_expense
    return {
        "metrics": metrics,
        "trend": trend,
        "category_expenses": metrics["category_expenses"],
        "category_breakdown": category_breakdown,
        "budget_vs_actual": budget_vs_actual,
        "budget_data_available": bool(budget_map),
        "goals": goal_calculations,
        "active_goals": active_goals,
        "period": {"start": period_start, "end": period_end, "preset": preset},
        "previous_period": {"start": previous_start, "end": previous_end},
        "comparison": {
            "income": {"amount": metrics["total_income"] - previous["total_income"], "percent": change(metrics["total_income"], previous["total_income"])},
            "expenses": {"amount": metrics["total_expenses"] - previous["total_expenses"], "percent": change(metrics["total_expenses"], previous["total_expenses"])},
            "savings": {"amount": metrics["total_savings"] - previous["total_savings"], "percent": change(metrics["total_savings"], previous["total_savings"])},
        },
        "alerts": alerts,
        "multiple_goals": {
            "total_required": total_required,
            "available_capacity": available_capacity,
            "shortfall": max(0, round(total_required - available_capacity, 2)),
        },
        "active_goal_count": len(active_goals),
        "insights": insights,
        "has_historical_data": len([item for item in trend if item["income"] or item["expenses"]]) >= 2,
        "financial_position_available": False,
    }
