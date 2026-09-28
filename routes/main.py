from datetime import date
from io import StringIO
import csv
from flask import Blueprint, flash, redirect, render_template, request, url_for, Response
from flask_login import current_user, login_required
from extensions import db
from models import Goal
from services.financial_engine import analytics_report, monthly_metrics

main_bp = Blueprint("main", __name__)

@main_bp.get("/")
def index():
    return render_template("index.html")

@main_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.name = request.form.get("name", "").strip() or current_user.name
        current_user.user_type = request.form.get("user_type", current_user.user_type)
        current_user.monthly_income_preference = float(request.form.get("monthly_income", 0) or 0)
        current_user.monthly_savings_target = float(request.form.get("savings_target", 0) or 0)
        current_user.financial_goal = request.form.get("financial_goal", "").strip()
        
        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("main.profile"))
        
    metrics = monthly_metrics(current_user.id)
    goals = Goal.query.filter_by(user_id=current_user.id).order_by(Goal.target_date.asc().nullslast(), Goal.created_at.desc()).all()
    return render_template("profile.html", metrics=metrics, goals=goals)

@main_bp.route("/reports", methods=["GET", "POST"])
@login_required
def reports():
    values = request.form if request.method == "POST" else request.args
    preset = values.get("preset", "this_month")
    try:
        start_date = date.fromisoformat(values["start_date"]) if values.get("start_date") else None
        end_date = date.fromisoformat(values["end_date"]) if values.get("end_date") else None
    except ValueError:
        flash("Choose valid custom dates.", "danger")
        start_date = end_date = None
        preset = "this_month"
    analytics = analytics_report(current_user.id, preset, start_date, end_date)
    return render_template("reports.html", metrics=analytics["metrics"], analytics=analytics, preset=preset, start_date=start_date, end_date=end_date)

@main_bp.post("/reports/generate")
@login_required
def generate_report():
    return reports()


@main_bp.get("/reports/export.csv")
@login_required
def export_report_csv():
    preset = request.args.get("preset", "this_month")
    start_date = date.fromisoformat(request.args["start_date"]) if request.args.get("start_date") else None
    end_date = date.fromisoformat(request.args["end_date"]) if request.args.get("end_date") else None
    analytics = analytics_report(current_user.id, preset, start_date, end_date)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["PaisaPath AI report", analytics["period"]["start"], analytics["period"]["end"]])
    writer.writerow(["Metric", "Amount", "Change vs previous period"])
    for key, label in (("total_income", "Income"), ("total_expenses", "Expenses"), ("total_savings", "Savings"), ("remaining_budget", "Budget remaining")):
        writer.writerow([label, analytics["metrics"][key], analytics["comparison"][key.replace("total_", "").replace("remaining_budget", "expenses")]["amount"] if key in {"total_income", "total_expenses", "total_savings"} else ""])
    writer.writerow([])
    writer.writerow(["Category", "Actual", "Budget", "Over budget"])
    for item in analytics["budget_vs_actual"]:
        writer.writerow([item["category"], item["actual"], item["budget"], item["over"]])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=paisapath-report.csv"})
