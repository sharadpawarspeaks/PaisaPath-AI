from datetime import date
from types import SimpleNamespace

from services.finance_calculator import calculate_goal, calculate_what_if


def make_income(amount=50000, effective_date=date(2027, 1, 1)):
    return SimpleNamespace(
        id=1,
        source="Salary",
        amount=amount,
        date=date(2026, 1, 1),
        annual_increase_percent=2,
        annual_increase_effective_date=effective_date,
    )


def make_goal(target_date=date(2026, 10, 30)):
    return SimpleNamespace(
        id=1,
        name="Samsung A22",
        target_amount=20000,
        current_amount=300,
        target_date=target_date,
    )


def test_salary_increment_after_goal_date_does_not_apply():
    result = calculate_goal(make_goal(), [make_income()], as_of=date(2026, 9, 26))

    assert result["current_salary"] == 50000
    assert result["next_salary"] == 51000
    assert result["applicable_salary"] == 50000
    assert result["salary_increment_affects_goal"] is False
    assert "after this goal's target date" in result["salary_explanation"]


def test_salary_increment_before_goal_date_applies_as_monthly_salary():
    goal = make_goal(date(2027, 10, 30))
    result = calculate_goal(goal, [make_income()], as_of=date(2026, 9, 26))

    assert result["applicable_salary"] == 51000
    assert result["salary_increment_affects_goal"] is True
    assert result["next_salary"] - result["current_salary"] == 1000


def test_goal_pace_uses_actual_remaining_days_and_units():
    result = calculate_goal(make_goal(), [], as_of=date(2026, 9, 26))

    assert result["remaining_amount"] == 19700
    assert result["progress_percentage"] == 1.5
    assert result["remaining_days"] == 34
    assert result["daily_required"] == round(19700 / 34, 2)
    assert result["weekly_required"] == round(19700 / 34 * 7, 2)
    assert result["monthly_required"] > 0


def test_what_if_is_read_only_and_uses_monthly_equivalent():
    goal = make_goal()
    result = calculate_what_if(goal, [], 10000, frequency="monthly", as_of=date(2026, 9, 26))

    assert result["scenario"] == {"amount": 10000.0, "frequency": "monthly"}
    assert result["current_savings_rate"] == 10000
    assert goal.current_amount == 300


def test_capacity_uses_all_recurring_income_minus_expenses():
    freelance = SimpleNamespace(id=2, source="Freelance", amount=12000, date=date(2026, 1, 1), frequency="Monthly", recurring=True, end_date=None)
    expense = SimpleNamespace(amount=35000, date=date(2026, 1, 1), frequency="Monthly", recurring=True, end_date=None)
    result = calculate_goal(make_goal(date(2027, 9, 26)), [make_income(), freelance], [expense], as_of=date(2026, 9, 26))

    assert result["normalized_monthly_income"] == 62000
    assert result["monthly_expenses"] == 35000
    assert result["available_goal_contribution"] == 27000
    assert result["feasibility_status"] == "FEASIBLE"


def test_no_deadline_goal_gets_estimated_completion_without_inventing_date():
    goal = make_goal(None)
    expense = SimpleNamespace(amount=35000, date=date(2026, 1, 1), frequency="Monthly", recurring=True, end_date=None)
    result = calculate_goal(goal, [make_income()], [expense], as_of=date(2026, 9, 26))

    assert result["target_date"] is None
    assert result["goal_status"] == "Estimated"
    assert result["feasibility_status"] == "ESTIMATED"
    assert result["projected_completion_date"] is not None
    assert result["estimated_months_to_goal"] is not None


def test_missing_expenses_is_insufficient_data():
    result = calculate_goal(make_goal(), [make_income()], [], as_of=date(2026, 9, 26))

    assert result["feasibility_status"] == "INSUFFICIENT DATA"
    assert result["available_goal_contribution"] == 0


def test_long_term_salary_projection_compounds_each_annual_increment():
    result = calculate_goal(make_goal(date(2029, 12, 31)), [make_income()], as_of=date(2026, 9, 26))

    assert result["projected_salary_at_target"] == 53060.4
