from datetime import date
from io import StringIO
import csv
from flask import Blueprint, flash, redirect, render_template, request, url_for, Response
from flask_login import current_user, login_required
from sqlalchemy import or_
from extensions import db
from models import Income, Expense, Budget, Goal
from services.budget_engine import CATEGORIES, recommended_budget
from services.financial_engine import monthly_metrics
from services.finance_calculator import calculate_goal, calculate_what_if

finance_bp = Blueprint("finance", __name__)

def positive(value):
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False

def parse_date(value):
    return date.fromisoformat(value) if value else date.today()

def parse_optional_date(value):
    return date.fromisoformat(value) if value else None


def filtered_transactions(model, user_id, values):
    query = model.query.filter_by(user_id=user_id)
    search = (values.get("search") or "").strip()
    start_date = parse_optional_date(values.get("start_date"))
    end_date = parse_optional_date(values.get("end_date"))
    if search:
        searchable_field = model.category if model is Expense else model.source
        query = query.filter(or_(model.description.ilike(f"%{search}%"), searchable_field.ilike(f"%{search}%")))
    if start_date:
        query = query.filter(model.date >= start_date)
    if end_date:
        query = query.filter(model.date <= end_date)
    if values.get("recurring") in {"yes", "no"}:
        query = query.filter(model.recurring.is_(values.get("recurring") == "yes"))
    if model is Income and values.get("source"):
        query = query.filter_by(source=values.get("source"))
    if model is Expense:
        if values.get("category"):
            query = query.filter_by(category=values.get("category"))
        if values.get("payment_method"):
            query = query.filter_by(payment_method=values.get("payment_method"))
    sort = values.get("sort", "newest")
    if sort == "oldest":
        query = query.order_by(model.date.asc())
    elif sort == "highest":
        query = query.order_by(model.amount.desc())
    elif sort == "lowest":
        query = query.order_by(model.amount.asc())
    else:
        query = query.order_by(model.date.desc())
    return query.all()

def goal_calculations(goals, user_id, as_of=None):
    incomes = Income.query.filter_by(user_id=user_id).all()
    expenses = Expense.query.filter_by(user_id=user_id).all()
    return [calculate_goal(goal, incomes, expenses=expenses, as_of=as_of) for goal in goals]

@finance_bp.route("/income", methods=["GET", "POST"])
@login_required
def income():
    if request.method == "POST":
        if not positive(request.form.get("amount")):
            flash("Income must be a positive amount.", "danger")
        else:
            source = request.form.get("source", "Other")
            increase = float(request.form.get("annual_increase_percent", 0) or 0) if source == "Salary" else 0
            increase_date = parse_date(request.form.get("annual_increase_effective_date")) if source == "Salary" and request.form.get("annual_increase_effective_date") else None
            if increase < 0 or increase > 100:
                flash("Annual salary increase must be between 0 and 100%.", "danger")
            else:
                frequency = request.form.get("frequency", "Monthly")
                db.session.add(Income(user_id=current_user.id, amount=float(request.form["amount"]), source=source, frequency=frequency, recurring=request.form.get("recurring") == "on" and frequency != "One-time", end_date=parse_optional_date(request.form.get("end_date")), annual_increase_percent=increase, annual_increase_effective_date=increase_date, date=parse_date(request.form.get("date")), description=request.form.get("description", "").strip()))
                db.session.commit()
                flash("Income added.", "success")
        return redirect(url_for("finance.income"))
    items = filtered_transactions(Income, current_user.id, request.args)
    return render_template("income.html", items=items, total=sum(item.amount for item in items))

@finance_bp.route("/income/delete/<int:item_id>", methods=["POST"])
@login_required
def delete_income(item_id):
    item = Income.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    db.session.delete(item); db.session.commit(); flash("Income removed.", "success")
    return redirect(url_for("finance.income"))

@finance_bp.post("/income/edit/<int:item_id>")
@login_required
def edit_income(item_id):
    item = Income.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    if positive(request.form.get("amount")):
        item.amount = float(request.form["amount"])
        item.source = request.form.get("source", item.source)
        increase = float(request.form.get("annual_increase_percent", 0) or 0) if item.source == "Salary" else 0
        if increase < 0 or increase > 100:
            flash("Annual salary increase must be between 0 and 100%.", "danger")
            return redirect(url_for("finance.income"))
        item.annual_increase_percent = increase
        item.annual_increase_effective_date = parse_date(request.form.get("annual_increase_effective_date")) if item.source == "Salary" and request.form.get("annual_increase_effective_date") else None
        item.date = parse_date(request.form.get("date"))
        item.description = request.form.get("description", item.description).strip()
        db.session.commit(); flash("Income updated.", "success")
    else:
        flash("Income must be a positive amount.", "danger")
    return redirect(url_for("finance.income"))

@finance_bp.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():
    if request.method == "POST":
        if not positive(request.form.get("amount")):
            flash("Expense must be a positive amount.", "danger")
        else:
            frequency = request.form.get("frequency", "Monthly")
            db.session.add(Expense(user_id=current_user.id, amount=float(request.form["amount"]), category=request.form.get("category", "Other"), frequency=frequency, recurring=request.form.get("recurring") == "on" and frequency != "One-time", end_date=parse_optional_date(request.form.get("end_date")), date=parse_date(request.form.get("date")), description=request.form.get("description", "").strip(), payment_method=request.form.get("payment_method", "UPI")))
            db.session.commit(); flash("Expense added.", "success")
        return redirect(url_for("finance.expenses"))
    items = filtered_transactions(Expense, current_user.id, request.args)
    return render_template("expenses.html", items=items, total=sum(item.amount for item in items), categories=CATEGORIES, options=CATEGORIES)

@finance_bp.post("/expenses/delete/<int:item_id>")
@login_required
def delete_expense(item_id):
    item = Expense.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    db.session.delete(item); db.session.commit(); flash("Expense removed.", "success")
    return redirect(url_for("finance.expenses"))


@finance_bp.get("/transactions/export.csv")
@login_required
def export_transactions_csv():
    kind = request.args.get("type", "expense")
    model = Income if kind == "income" else Expense
    items = filtered_transactions(model, current_user.id, request.args)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Type", "Date", "Source/Category", "Amount", "Frequency", "Recurring", "Payment method", "Description"])
    for item in items:
        writer.writerow(["Income" if model is Income else "Expense", item.date.isoformat(), item.source if model is Income else item.category, item.amount, item.frequency, item.recurring, getattr(item, "payment_method", ""), item.description or ""])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=paisapath-{kind}.csv"})

@finance_bp.post("/expenses/edit/<int:item_id>")
@login_required
def edit_expense(item_id):
    item = Expense.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    if positive(request.form.get("amount")):
        item.amount = float(request.form["amount"])
        item.category = request.form.get("category", item.category)
        item.date = parse_date(request.form.get("date"))
        item.description = request.form.get("description", item.description).strip()
        item.payment_method = request.form.get("payment_method", item.payment_method)
        db.session.commit(); flash("Expense updated.", "success")
    else:
        flash("Expense must be a positive amount.", "danger")
    return redirect(url_for("finance.expenses"))

@finance_bp.route("/budget", methods=["GET", "POST"])
@login_required
def budget():
    today = date.today()
    if request.method == "POST":
        category = request.form.get("category", "Other")
        amount = float(request.form.get("amount", 0) or 0)
        if amount <= 0: flash("Budget must be positive.", "danger")
        else:
            item = Budget.query.filter_by(user_id=current_user.id, category=category, month=today.month, year=today.year).first()
            if item: item.amount = amount
            else: db.session.add(Budget(user_id=current_user.id, category=category, amount=amount, month=today.month, year=today.year))
            db.session.commit(); flash("Budget saved.", "success")
        return redirect(url_for("finance.budget"))
    metrics = monthly_metrics(current_user.id)
    budgets = Budget.query.filter_by(user_id=current_user.id, month=today.month, year=today.year).all()
    return render_template("budget.html", budgets=budgets, metrics=metrics, categories=CATEGORIES)

@finance_bp.post("/budget/generate")
@login_required
def generate_budget():
    today = date.today()
    for category, amount in recommended_budget(current_user, today.month, today.year).items():
        item = Budget.query.filter_by(user_id=current_user.id, category=category, month=today.month, year=today.year).first()
        if item: item.amount = amount
        else: db.session.add(Budget(user_id=current_user.id, category=category, amount=amount, month=today.month, year=today.year))
    db.session.commit(); flash("Suggested budget generated from your income and spending profile.", "success")
    return redirect(url_for("finance.budget"))

@finance_bp.post("/budget/update")
@login_required
def update_budget():
    return budget()

@finance_bp.route("/goals", methods=["GET", "POST"])
@login_required
def goals():
    if request.method == "POST":
        target = float(request.form.get("target_amount", 0) or 0)
        if not request.form.get("name") or target <= 0: flash("Provide a goal name and positive target.", "danger")
        else:
            db.session.add(Goal(user_id=current_user.id, name=request.form["name"].strip(), target_amount=target, current_amount=float(request.form.get("current_amount", 0) or 0), target_date=parse_optional_date(request.form.get("target_date")), description=request.form.get("description", "").strip()))
            db.session.commit(); flash("Goal created.", "success")
        return redirect(url_for("finance.goals"))
    goals = Goal.query.filter_by(user_id=current_user.id).order_by(Goal.created_at.desc()).all()
    calculations = goal_calculations(goals, current_user.id)
    return render_template("goals.html", goals=goals, goal_calculation_map={calculation["goal_id"]: calculation for calculation in calculations})

@finance_bp.post("/goals/contribute/<int:goal_id>")
@login_required
def contribute(goal_id):
    goal = Goal.query.filter_by(id=goal_id, user_id=current_user.id).first_or_404()
    amount = float(request.form.get("amount", 0) or 0)
    if amount > 0: goal.current_amount = min(goal.target_amount, goal.current_amount + amount); db.session.commit(); flash("Contribution recorded.", "success")
    return redirect(url_for("finance.goals"))

@finance_bp.route("/goals/<int:goal_id>", methods=["GET", "POST"])
@login_required
def goal_detail(goal_id):
    goal = Goal.query.filter_by(id=goal_id, user_id=current_user.id).first_or_404()
    incomes = Income.query.filter_by(user_id=current_user.id).all()
    expenses = Expense.query.filter_by(user_id=current_user.id).all()
    calculation = calculate_goal(goal, incomes, expenses=expenses)
    scenario = None
    if request.method == "POST":
        try:
            amount = float(request.form.get("amount", 0))
            frequency = request.form.get("frequency", "monthly")
            scenario = calculate_what_if(goal, incomes, amount, frequency=frequency)
        except (TypeError, ValueError):
            flash("Enter a valid non-negative daily, weekly, or monthly contribution.", "danger")
    return render_template("goal_detail.html", goal=goal, calculation=calculation, scenario=scenario)

@finance_bp.post("/goals/delete/<int:goal_id>")
@login_required
def delete_goal(goal_id):
    goal = Goal.query.filter_by(id=goal_id, user_id=current_user.id).first_or_404(); db.session.delete(goal); db.session.commit(); flash("Goal removed.", "success")
    return redirect(url_for("finance.goals"))
