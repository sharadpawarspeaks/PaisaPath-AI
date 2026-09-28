from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from math import ceil

AVERAGE_DAYS_PER_YEAR = 365.2425
AVERAGE_DAYS_PER_MONTH = AVERAGE_DAYS_PER_YEAR / 12
FREQUENCY_TO_MONTHS = {
    "daily": 365.2425 / 12,
    "weekly": 52.1775 / 12,
    "monthly": 1,
    "quarterly": 1 / 3,
    "yearly": 1 / 12,
    "one-time": 0,
}


def _round(value):
    return round(float(value or 0), 2)


def _frequency(value):
    return str(value or "Monthly").strip().lower().replace(" ", "-")


def monthly_value(item, as_of):
    """Normalize a recurring record to a monthly value when active."""
    end_date = getattr(item, "end_date", None)
    if item.date > as_of or (end_date and as_of > end_date):
        return 0.0
    frequency = _frequency(getattr(item, "frequency", "Monthly"))
    if not getattr(item, "recurring", True):
        return 0.0
    factor = FREQUENCY_TO_MONTHS.get(frequency, 1)
    return item.amount * factor


def savings_capacity(incomes, expenses, as_of):
    monthly_income = sum(monthly_value(item, as_of) for item in incomes)
    monthly_expenses = sum(monthly_value(item, as_of) for item in expenses)
    return {
        "monthly_income": _round(monthly_income),
        "annual_income": _round(monthly_income * 12),
        "monthly_expenses": _round(monthly_expenses),
        "available_goal_contribution": _round(max(0, monthly_income - monthly_expenses)),
        "expense_data_available": bool(expenses),
    }


def salary_snapshot(incomes, as_of):
    """Return the salary effective on the supplied date, without future records."""
    salaries = [income for income in incomes if income.source == "Salary" and income.date <= as_of]
    salary = max(salaries, key=lambda item: (item.date, item.id or 0), default=None)
    if salary is None:
        return {
            "current_salary": 0.0,
            "annual_salary": 0.0,
            "increment_percent": 0.0,
            "increment_effective_date": None,
            "next_salary": 0.0,
        }

    effective_date = salary.annual_increase_effective_date
    increment_percent = max(0.0, salary.annual_increase_percent or 0.0)
    next_salary = salary.amount * (1 + increment_percent / 100) if effective_date else salary.amount
    return {
        "current_salary": _round(salary.amount),
        "annual_salary": _round(salary.amount * 12),
        "increment_percent": _round(increment_percent),
        "increment_effective_date": effective_date,
        "next_salary": _round(next_salary),
    }


def salary_projection(salary, target_date):
    if not salary or not salary["increment_effective_date"] or not target_date:
        return salary["current_salary"] if salary else 0.0
    effective = salary["increment_effective_date"]
    if target_date < effective:
        return salary["current_salary"]
    increments = target_date.year - effective.year
    if (target_date.month, target_date.day) < (effective.month, effective.day):
        increments -= 1
    return _round(salary["current_salary"] * (1 + salary["increment_percent"] / 100) ** max(0, increments + 1))


def _calendar_months_remaining(current_date, target_date):
    if target_date <= current_date:
        return 0.0
    whole_months = (target_date.year - current_date.year) * 12 + target_date.month - current_date.month
    anchor_month = current_date.month + whole_months
    anchor_year = current_date.year + (anchor_month - 1) // 12
    anchor_month = (anchor_month - 1) % 12 + 1
    anchor_day = min(current_date.day, monthrange(anchor_year, anchor_month)[1])
    anchor = date(anchor_year, anchor_month, anchor_day)
    if anchor > target_date:
        whole_months -= 1
        anchor_month = current_date.month + whole_months
        anchor_year = current_date.year + (anchor_month - 1) // 12
        anchor_month = (anchor_month - 1) % 12 + 1
        anchor = date(anchor_year, anchor_month, min(current_date.day, monthrange(anchor_year, anchor_month)[1]))
    remainder_days = (target_date - anchor).days
    return whole_months + remainder_days / AVERAGE_DAYS_PER_MONTH


def calculate_goal(goal, incomes, expenses=None, as_of=None, current_savings_rate=0):
    current_date = as_of or date.today()
    target_date = goal.target_date
    remaining = max(0.0, goal.target_amount - goal.current_amount)
    progress = min(100.0, _round((goal.current_amount / goal.target_amount) * 100)) if goal.target_amount else 0.0
    remaining_days = max(0, (target_date - current_date).days) if target_date else None
    remaining_weeks = ceil(remaining_days / 7) if remaining_days else 0
    remaining_months = _calendar_months_remaining(current_date, target_date) if target_date else None
    remaining_years = remaining_days / AVERAGE_DAYS_PER_YEAR if remaining_days else 0

    daily_required = remaining / remaining_days if remaining and remaining_days else remaining
    weekly_required = daily_required * 7 if remaining_days else remaining
    monthly_required = remaining / remaining_months if remaining and remaining_months else remaining
    annualized_required = daily_required * AVERAGE_DAYS_PER_YEAR if remaining_days else remaining

    capacity = savings_capacity(incomes, expenses or [], current_date) if expenses is not None else {
        "monthly_income": 0,
        "annual_income": 0,
        "monthly_expenses": 0,
        "available_goal_contribution": max(0.0, float(current_savings_rate or 0)),
        "expense_data_available": False,
    }
    available = capacity["available_goal_contribution"] if capacity["expense_data_available"] else max(0.0, float(current_savings_rate or 0))
    salary = salary_snapshot(incomes, current_date)
    increment_date = salary["increment_effective_date"]
    increment_affects_goal = bool(increment_date and target_date and increment_date <= target_date)
    applicable_salary = salary["next_salary"] if increment_affects_goal else salary["current_salary"]
    projected_salary_at_target = salary_projection(salary, target_date) if target_date else salary["current_salary"]
    salary_explanation = None
    if increment_date and target_date and not increment_affects_goal:
        salary_explanation = "Your salary increment begins after this goal's target date, so your current salary is used."

    current_rate = available
    shortfall = max(0.0, monthly_required - current_rate)
    surplus = max(0.0, current_rate - monthly_required)
    if not remaining:
        status = "Completed"
    elif expenses is not None and not capacity["expense_data_available"]:
        status = "Insufficient Data"
    elif not target_date:
        status = "Estimated"
    elif not remaining_days:
        status = "Behind Target"
    elif current_rate >= monthly_required:
        status = "On Track"
    else:
        status = "Needs Attention"

    projected_completion = None
    if remaining and current_rate > 0:
        projected_days = ceil(remaining / (current_rate / AVERAGE_DAYS_PER_MONTH))
        projected_completion = current_date + timedelta(days=projected_days)

    estimated_days = ceil(remaining / (current_rate / AVERAGE_DAYS_PER_MONTH)) if remaining and current_rate > 0 else None
    estimated_weeks = ceil(estimated_days / 7) if estimated_days else None
    estimated_months = estimated_days / AVERAGE_DAYS_PER_MONTH if estimated_days else None
    estimated_years = estimated_days / AVERAGE_DAYS_PER_YEAR if estimated_days else None

    projection = []
    projection_end = target_date or projected_completion
    if projection_end and (projection_end - current_date).days > 365 and capacity["expense_data_available"]:
        projected_cumulative = _round(goal.current_amount)
        for year in range(current_date.year, min(projection_end.year, current_date.year + 25) + 1):
            year_date = date(year, 12, 31)
            monthly_income = salary_projection(salary, year_date) + max(0, capacity["monthly_income"] - salary["current_salary"])
            annual_income = _round(monthly_income * 12)
            annual_expenses = _round(capacity["monthly_expenses"] * 12)
            available_savings = _round(max(0, annual_income - annual_expenses))
            projected_cumulative = _round(min(goal.target_amount, projected_cumulative + available_savings))
            projection.append({
                "year": year,
                "monthly_income": _round(monthly_income),
                "annual_income": annual_income,
                "projected_expenses": annual_expenses,
                "available_savings": available_savings,
                "cumulative_savings": projected_cumulative,
                "goal_remaining": _round(max(0, goal.target_amount - projected_cumulative)),
            })

    return {
        "goal_id": goal.id,
        "goal_name": goal.name,
        "goal_amount": _round(goal.target_amount),
        "amount_saved": _round(goal.current_amount),
        "remaining_amount": _round(remaining),
        "progress_percentage": progress,
        "current_date": current_date,
        "target_date": target_date,
        "remaining_days": remaining_days,
        "remaining_weeks": remaining_weeks,
        "remaining_months": _round(remaining_months) if remaining_months is not None else None,
        "remaining_years": _round(remaining_years),
        "daily_required": _round(daily_required),
        "weekly_required": _round(weekly_required),
        "monthly_required": _round(monthly_required),
        "annualized_required": _round(annualized_required),
        "current_savings_rate": _round(current_rate),
        "required_savings_rate": _round(monthly_required),
        "savings_shortfall": _round(shortfall),
        "savings_surplus": _round(surplus),
        "projected_completion_date": projected_completion,
        "goal_status": status,
        "feasibility_status": "INSUFFICIENT DATA" if status == "Insufficient Data" else ("ESTIMATED" if not target_date and current_rate > 0 else ("FEASIBLE" if not remaining or (target_date and current_rate >= monthly_required) else "NOT FEASIBLE AT CURRENT CAPACITY")),
        "feasibility_label": "Currently Feasible" if not remaining or (target_date and current_rate >= monthly_required) else ("Insufficient Data" if status == "Insufficient Data" else ("Challenging" if current_rate > 0 else "Not Feasible at Current Capacity")),
        "feasibility_reason": "Add monthly expense information to estimate realistic goal capacity." if status == "Insufficient Data" else None,
        "normalized_monthly_income": capacity["monthly_income"],
        "normalized_annual_income": capacity["annual_income"],
        "monthly_expenses": capacity["monthly_expenses"],
        "available_goal_contribution": _round(current_rate),
        "estimated_days_to_goal": estimated_days,
        "estimated_weeks_to_goal": estimated_weeks,
        "estimated_months_to_goal": _round(estimated_months) if estimated_months else None,
        "estimated_years_to_goal": _round(estimated_years) if estimated_years else None,
        "applicable_salary": _round(applicable_salary),
        "current_salary": salary["current_salary"],
        "next_salary": salary["next_salary"],
        "projected_salary_at_target": projected_salary_at_target,
        "salary_increment_percentage": salary["increment_percent"],
        "salary_increment_effective_date": increment_date,
        "salary_increment_affects_goal": increment_affects_goal,
        "salary_explanation": salary_explanation,
        "calculation_timestamp": datetime.now(timezone.utc),
        "long_term_projection": projection,
    }


def calculate_what_if(goal, incomes, contribution_amount, frequency="monthly", as_of=None):
    """Calculate a read-only scenario using the same goal calculation rules."""
    frequency_days = {"daily": 1, "weekly": 7, "monthly": AVERAGE_DAYS_PER_MONTH}
    if frequency not in frequency_days or contribution_amount < 0:
        raise ValueError("Use daily, weekly, or monthly with a non-negative contribution.")
    monthly_rate = contribution_amount * AVERAGE_DAYS_PER_MONTH / frequency_days[frequency]
    result = calculate_goal(goal, incomes, as_of=as_of, current_savings_rate=monthly_rate)
    result["scenario"] = {"amount": _round(contribution_amount), "frequency": frequency}
    return result
