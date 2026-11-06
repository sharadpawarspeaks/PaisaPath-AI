import os
import json
import re
from datetime import date
from flask import current_app
from extensions import db
from models import Goal, Expense, Income
from services.finance_calculator import calculate_goal

# Financial categories classification
ESSENTIAL_CATEGORIES = {"Rent", "Food", "Transport", "Education", "Healthcare", "Utilities", "Household"}
DISCRETIONARY_CATEGORIES = {"Shopping", "Entertainment", "Subscriptions", "Other"}


def get_user_financial_context(user, metrics, calculations=None):
    """Gathers full financial context for a user for AI analysis."""
    today = date.today()
    goals = Goal.query.filter_by(user_id=user.id).order_by(Goal.created_at.desc()).all()
    if calculations is None:
        incomes = Income.query.filter_by(user_id=user.id).all()
        expenses = Expense.query.filter_by(user_id=user.id).all()
        calculations = [calculate_goal(goal, incomes, expenses=expenses, as_of=today, current_savings_rate=metrics.get("total_savings", 0)) for goal in goals]
    recent_expenses = Expense.query.filter_by(user_id=user.id).order_by(Expense.date.desc()).limit(10).all()
    
    # Calculate essential vs discretionary breakdown
    cat_expenses = metrics.get("category_expenses", {})
    total_exp = metrics.get("total_expenses", 0)
    
    essential_spend = sum(amt for cat, amt in cat_expenses.items() if cat in ESSENTIAL_CATEGORIES)
    discretionary_spend = sum(amt for cat, amt in cat_expenses.items() if cat in DISCRETIONARY_CATEGORIES)
    
    effective_income = metrics.get("total_income", 0) or getattr(user, "monthly_income_preference", 0) or 0
    
    goals_data = [{
        "name": calculation["goal_name"],
        "target_amount": calculation["goal_amount"],
        "current_amount": calculation["amount_saved"],
        "remaining": calculation["remaining_amount"],
        "progress": calculation["progress_percentage"],
        "target_date": calculation["target_date"].strftime("%d %b %Y") if calculation["target_date"] else None,
        "months_remaining": calculation["remaining_months"],
        "days_remaining": calculation["remaining_days"],
        "monthly_savings_needed": calculation["monthly_required"],
        "daily_required": calculation["daily_required"],
        "weekly_required": calculation["weekly_required"],
        "goal_status": calculation["goal_status"],
        "applicable_salary": calculation["applicable_salary"],
        "next_salary": calculation["next_salary"],
        "projected_salary_at_target": calculation["projected_salary_at_target"],
        "salary_increment_affects_goal": calculation["salary_increment_affects_goal"],
        "available_goal_contribution": calculation["available_goal_contribution"],
        "feasibility_status": calculation["feasibility_status"],
        "is_achieved": calculation["goal_status"] == "Completed"
    } for calculation in calculations]
    
    recent_exp_data = [{
        "category": e.category,
        "amount": e.amount,
        "date": e.date.isoformat(),
        "description": e.description,
        "payment_method": e.payment_method
    } for e in recent_expenses]
    
    return {
        "user_id": user.get_id(),
        "user_name": user.name,
        "user_type": getattr(user, "user_type", "Salaried Professional"),
        "currency": getattr(user, "currency", "INR"),
        "monthly_income": effective_income,
        "recorded_income": metrics.get("total_income", 0),
        "total_expenses": total_exp,
        "total_savings": metrics.get("total_savings", effective_income - total_exp),
        "savings_rate": metrics.get("savings_rate", 0),
        "savings_target": getattr(user, "monthly_savings_target", 0) or 0,
        "financial_goal": getattr(user, "financial_goal", "") or "",
        "category_expenses": cat_expenses,
        "essential_spending": essential_spend,
        "discretionary_spending": discretionary_spend,
        "overspending": metrics.get("overspending", {}),
        "remaining_budget": metrics.get("remaining_budget", 0),
        "goals": goals_data,
        "recent_expenses": recent_exp_data
    }


def smart_local_financial_advisor(user, metrics, question=None):
    """
    Intelligent rule & NLP-based financial advisor that provides deep,
    actionable, data-grounded insights when Gemini API key is not present.
    """
    ctx = get_user_financial_context(user, metrics)
    total_exp = ctx["total_expenses"]
    income = ctx["monthly_income"]
    cat_expenses = ctx["category_expenses"]
    overspending = ctx["overspending"]
    savings_rate = ctx["savings_rate"]
    goals = ctx["goals"]
    user_type = ctx["user_type"]
    
    q = (question or "").strip().lower()
    
    # Identify top categories
    sorted_cats = sorted(cat_expenses.items(), key=lambda x: x[1], reverse=True)
    top_cat = sorted_cats[0] if sorted_cats else ("None", 0)
    top_discretionary = [(c, a) for c, a in sorted_cats if c in DISCRETIONARY_CATEGORIES]
    highest_disc = top_discretionary[0] if top_discretionary else None

    # Goal metrics calculation
    active_goals = [g for g in goals if not g.get("is_achieved")]
    total_monthly_goal_need = sum(g.get("monthly_savings_needed") or 0 for g in active_goals)

    # Intent 1: Where to save money / cut expenses / reduce spending
    if any(phrase in q for phrase in ["save money", "where can i save", "where dose i can save", "cut", "reduce", "spend less", "save more", "trim", "lower"]):
        if total_exp == 0:
            summary = "You have no recorded expenses yet this month."
            recommendation = "Start tracking your daily expenses to identify spending leaks and unlock personalized savings opportunities."
            priorities = ["Record your daily expenses", "Set a monthly savings target in your Profile", "Create your first emergency fund goal"]
            reply = "You currently have no expenses recorded for this month. Once you log a few expenses (like Rent, Groceries, Shopping, or Subscriptions), I can analyze your spending patterns and identify exact rupee savings for you!"
        else:
            disc_sum = ctx["discretionary_spending"]
            disc_pct = round((disc_sum / total_exp * 100), 1) if total_exp else 0
            
            savings_opportunities = []
            if highest_disc and highest_disc[1] > 0:
                potential_disc_save = round(highest_disc[1] * 0.25)
                savings_opportunities.append(f"**{highest_disc[0]} (Current: ₹{highest_disc[1]:,.0f})**: Trimming non-essential {highest_disc[0].lower()} purchases by 25% frees up **₹{potential_disc_save:,.0f}/month**.")
            
            food_spend = cat_expenses.get("Food", 0)
            if food_spend > 0:
                potential_food_save = round(food_spend * 0.15)
                savings_opportunities.append(f"**Food & Dining (Current: ₹{food_spend:,.0f})**: Planning meals and minimizing delivery/dining out by 15% recovers **₹{potential_food_save:,.0f}/month**.")
            
            sub_spend = cat_expenses.get("Subscriptions", 0)
            if sub_spend > 0:
                savings_opportunities.append(f"**Subscriptions (Current: ₹{sub_spend:,.0f})**: Audit active memberships and pause unused streaming/app plans.")
                
            rent_spend = cat_expenses.get("Rent", 0)
            if rent_spend > 0:
                savings_opportunities.append(f"**Rent / Housing (Current: ₹{rent_spend:,.0f})**: Fixed essential cost ({round(rent_spend/total_exp*100)}% of expenses). Keep this fixed and focus optimizations on variable categories.")

            if not savings_opportunities:
                savings_opportunities.append(f"**Top Category ({top_cat[0]}: ₹{top_cat[1]:,.0f})**: Review individual transactions for any recurring unnecessary expenses.")

            summary = f"Identified top savings opportunities in {highest_disc[0] if highest_disc else top_cat[0]} and variable spending."
            recommendation = f"By trimming 20-25% from discretionary spending (₹{disc_sum:,.0f} total), you can save an extra ₹{round(disc_sum * 0.22):,.0f} each month to fund your goals."
            
            priorities = [
                f"Cap {highest_disc[0] if highest_disc else 'discretionary'} spending with a weekly cash envelope or UPI limit",
                "Apply the 48-hour rule before buying any non-essential items over ₹1,000",
                f"Redirect savings directly to your active goals (₹{total_monthly_goal_need:,.0f}/mo needed)" if total_monthly_goal_need > 0 else "Automate a direct transfer to savings on payday"
            ]
            
            opp_text = "\n".join([f"- {s}" for s in savings_opportunities])
            goal_redirect_note = f"\n\n#### 🎯 Funding Your Goals:\nYou need **₹{total_monthly_goal_need:,.0f}/month** to reach all your active goals by their target dates. Cutting ₹{round(disc_sum * 0.22):,.0f}/mo in lifestyle expenses directly covers a major share of your goal savings requirement!" if total_monthly_goal_need > 0 else ""
            
            reply = f"""### 💡 Personalized Savings Breakdown

Based on your current recorded spending of **₹{total_exp:,.0f}**, here are the most effective places to save money:

{opp_text}

#### 🎯 Recommended Action Plan:
1. **Discretionary Spending**: You spend **₹{disc_sum:,.0f}** ({disc_pct}% of total expenses) on lifestyle & discretionary items. Cutting this by just 20% puts **₹{round(disc_sum * 0.2):,.0f}** straight into your savings!
2. **Weekly Spending Limit**: Set a firm weekly budget for discretionary shopping so you don't overspend towards the end of the month.
3. **Automate Savings**: Move your savings to your goal funds as soon as your income arrives.{goal_redirect_note}"""

        return {"summary": summary, "recommendation": recommendation, "priorities": priorities, "reply": reply, "source": "Intelligent Financial Advisor Engine"}

    # Intent 2: 50/30/20 Rule or Budgeting Advice
    elif any(phrase in q for phrase in ["50/30/20", "50 30 20", "budget rule", "how to budget", "ideal budget"]):
        base_income = income if income > 0 else total_exp * 1.25
        needs_target = base_income * 0.50
        wants_target = base_income * 0.30
        savings_target = base_income * 0.20
        
        ess = ctx["essential_spending"]
        disc = ctx["discretionary_spending"]
        
        summary = f"The 50/30/20 benchmark suggests: Needs ₹{needs_target:,.0f}, Wants ₹{wants_target:,.0f}, Savings ₹{savings_target:,.0f}."
        recommendation = f"Your current essentials are ₹{ess:,.0f} ({round(ess/base_income*100 if base_income else 0)}%) and wants are ₹{disc:,.0f} ({round(disc/base_income*100 if base_income else 0)}%)."
        priorities = [
            f"Keep essential Needs within ₹{needs_target:,.0f} (50%)",
            f"Cap lifestyle Wants at ₹{wants_target:,.0f} (30%)",
            f"Direct at least ₹{savings_target:,.0f} (20%) into your savings and active goals"
        ]
        
        goal_note = f"\n\n**Goal Check**: You currently require **₹{total_monthly_goal_need:,.0f}/month** across your active goals. Your 20% savings target of **₹{savings_target:,.0f}** {'covers this comfortably! 🎉' if savings_target >= total_monthly_goal_need else 'is slightly below your target date timeline. Consider increasing savings or trimming wants.'}" if total_monthly_goal_need > 0 else ""
        
        reply = f"""### ⚖️ 50/30/20 Budget Blueprint

For your monthly profile (Base Income: **₹{base_income:,.0f}**), here is how your money should ideally be distributed:

| Category | Recommended (50/30/20) | Your Current Spending | Status |
| :--- | :--- | :--- | :--- |
| **Needs (50%)** (Rent, Food, Utilities) | **₹{needs_target:,.0f}** | ₹{ess:,.0f} | {'✅ On Track' if ess <= needs_target else '⚠️ High'} |
| **Wants (30%)** (Shopping, Entertainment) | **₹{wants_target:,.0f}** | ₹{disc:,.0f} | {'✅ Healthy' if disc <= wants_target else '⚠️ Needs Trimming'} |
| **Savings (20%)** (Emergency Fund & Goals) | **₹{savings_target:,.0f}** | ₹{max(0, base_income - total_exp):,.0f} | {'✅ Target Met' if savings_rate >= 20 else '⚡ Focus on Boosting'} |

**Next Step**: Use the **Budget** tab to set hard limits for each category matching this distribution.{goal_note}"""
        return {"summary": summary, "recommendation": recommendation, "priorities": priorities, "reply": reply, "source": "Intelligent Financial Advisor Engine"}

    # Intent 3: Goals / Emergency Fund / Savings Target / Target Dates / Monthly savings needed
    elif any(phrase in q for phrase in ["goal", "emergency fund", "target", "buffer", "milestone", "save for", "target date", "save per month", "per month"]):
        if goals:
            primary_goal = goals[0]
            summary = f"You have {len(goals)} active goal(s). Total monthly savings required to hit all target dates: ₹{total_monthly_goal_need:,.0f}/mo."
            recommendation = f"Save ₹{total_monthly_goal_need:,.0f}/month across your active goals to reach all milestones by their target dates."
            
            goal_table_rows = []
            for g in goals:
                t_date = g.get("target_date") or "No deadline"
                mo_left = g.get("months_remaining")
                mo_str = f" ({mo_left} mo left)" if mo_left is not None and mo_left > 0 else (" (Due this month)" if mo_left == 0 else "")
                mo_need = g.get("monthly_savings_needed") or 0
                status_str = "🎉 Achieved" if g.get("is_achieved") else (f"**₹{mo_need:,.0f}/mo**" if mo_need > 0 else "Completed")
                goal_table_rows.append(f"| **{g['name']}** | {t_date}{mo_str} | ₹{g['current_amount']:,.0f} / ₹{g['target_amount']:,.0f} ({g['progress']}%) | ₹{g['remaining']:,.0f} | {status_str} |")
            
            table_text = "\n".join(goal_table_rows)
            
            priorities = [
                f"Automate monthly contributions of ₹{total_monthly_goal_need:,.0f} towards active goals",
                f"Prioritize '{primary_goal['name']}' ({primary_goal.get('target_date', 'Ongoing')} · ₹{primary_goal.get('monthly_savings_needed', 0):,.0f}/mo)",
                "Trim discretionary spending to ensure target dates are met without strain"
            ]
            
            net_save = ctx["total_savings"]
            feasibility_text = f"Your current estimated net monthly savings is **₹{net_save:,.0f}**, which {'**comfortably covers** your total goal requirement! 🎉' if net_save >= total_monthly_goal_need else f'is **₹{total_monthly_goal_need - net_save:,.0f} below** your required pace. Reducing discretionary expenses will help close this gap.'}"
            
            reply = f"""### 🎯 Active Goals & Target Date Roadmap

Here is the exact monthly savings breakdown required to reach your goals on time:

| Goal Name | Target Date | Progress | Remaining | Monthly Savings Needed |
| :--- | :--- | :--- | :--- | :--- |
{table_text}

#### 💡 Action Plan & Feasibility:
1. **Total Monthly Goal Requirement**: **₹{total_monthly_goal_need:,.0f} / month** across all active goals.
2. **Current Savings Capability**: {feasibility_text}
3. **Automate Transfers**: Set up an automatic transfer on the day your salary arrives to ensure consistent progress towards each goal's deadline."""
        else:
            rec_emergency = (total_exp * 3) if total_exp > 0 else 50000
            summary = f"Recommended starting goal: Build a 3-month Emergency Fund of ₹{rec_emergency:,.0f}."
            recommendation = "Having an emergency cushion gives you peace of mind and prevents relying on debt during unexpected expenses."
            priorities = [
                "Create an 'Emergency Fund' goal in the Goals section",
                f"Set target to ₹{rec_emergency:,.0f} (3 months of living costs)",
                "Deposit a small starting contribution this week"
            ]
            reply = f"""### 🛡️ Building Your Financial Safety Net

You haven't set up any active goals yet. The single most important financial milestone is an **Emergency Fund**:

- **Recommended Target**: **₹{rec_emergency:,.0f}** (covers 3 months of essential living expenses).
- **How to start**: Head over to the **Goals** tab, create a goal named *'Emergency Fund'*, set a target date (e.g., 6 months from now), and start with a modest initial deposit!"""

        return {"summary": summary, "recommendation": recommendation, "priorities": priorities, "reply": reply, "source": "Intelligent Financial Advisor Engine"}

    # Intent 4: Category Specific Questions (Rent, Food, Shopping, etc.)
    matched_cat = None
    for cat in cat_expenses:
        if cat.lower() in q:
            matched_cat = cat
            break
            
    if matched_cat:
        cat_amt = cat_expenses[matched_cat]
        cat_pct = round((cat_amt / total_exp * 100), 1) if total_exp else 0
        summary = f"{matched_cat} accounts for ₹{cat_amt:,.0f} ({cat_pct}% of total monthly spending)."
        
        if matched_cat in ["Shopping", "Entertainment", "Subscriptions"]:
            recommendation = f"Set a strict monthly ceiling on {matched_cat} to protect your savings rate."
            priorities = [
                f"Limit {matched_cat} to under {round(cat_amt * 0.75):,.0f} next month",
                "Wait 48 hours before non-essential purchases",
                "Check for promotional discounts and alternatives"
            ]
        elif matched_cat in ["Food"]:
            recommendation = "Optimize grocery shopping and reduce frequent food delivery orders."
            priorities = [
                "Plan weekly meals and buy groceries in bulk",
                "Limit food delivery apps to 1-2 times per week",
                "Track individual grocery bills to catch price spikes"
            ]
        else:
            recommendation = f"Maintain stable records for {matched_cat} and plan ahead for annual increases."
            priorities = [
                f"Verify {matched_cat} payments are tracked on schedule",
                "Compare utility/service providers for better tariffs",
                "Factor seasonal variations into your budget"
            ]
            
        reply = f"""### 🔍 Analysis for {matched_cat}

- **Current Spend**: **₹{cat_amt:,.0f}**
- **Share of Expenses**: **{cat_pct}%** of your total monthly outflow
- **Category Type**: *{'Discretionary (Flexible)' if matched_cat in DISCRETIONARY_CATEGORIES else 'Essential (Fixed/Semi-variable)'}*

#### 💡 Actionable Advice:
{recommendation}
- By setting a monthly budget limit in the **Budget** tab, PaisaPath AI will alert you before you exceed your target."""
        return {"summary": summary, "recommendation": recommendation, "priorities": priorities, "reply": reply, "source": "Intelligent Financial Advisor Engine"}

    # Default / General Financial Health Overview
    goals_note_overview = f"\n- **Active Goals**: You need **₹{total_monthly_goal_need:,.0f}/month** across {len(active_goals)} active goal(s) to hit all target dates on time." if total_monthly_goal_need > 0 else ""
    
    if not income and total_exp > 0:
        summary = f"Total expenses this month: ₹{total_exp:,.0f}. Top category: {top_cat[0]} (₹{top_cat[1]:,.0f})."
        recommendation = f"Your highest expense is {top_cat[0]}. Add your monthly income in the Income tab to calculate your exact savings rate and get complete 50/30/20 metrics."
        priorities = [
            "Log your monthly salary or earnings in the Income tab",
            f"Review {top_cat[0]} spending (₹{top_cat[1]:,.0f})",
            "Set category budget limits"
        ]
        reply = f"""### 📊 Monthly Financial Overview

Here is your current snapshot based on **₹{total_exp:,.0f}** in recorded expenses:

- **Top Spending Driver**: **{top_cat[0]}** at **₹{top_cat[1]:,.0f}** ({round(top_cat[1]/total_exp*100 if total_exp else 0)}% of total).
- **Essential vs Discretionary**: You have **₹{ctx['essential_spending']:,.0f}** in essentials and **₹{ctx['discretionary_spending']:,.0f}** in discretionary spending.{goals_note_overview}
- **Next Priority**: Log your income in the **Income** section to unlock your automated savings rate calculation!

Feel free to ask me questions like:
- *"Where can I save more money?"*
- *"How much should I save per month for my goals?"*
- *"Calculate my 50/30/20 budget"*"""
    elif overspending:
        ov_cat, ov_amt = max(overspending.items(), key=lambda x: x[1])
        summary = f"{ov_cat} is over budget by ₹{ov_amt:,.0f}. Monthly savings rate: {savings_rate:.1f}%."
        recommendation = f"Pause discretionary {ov_cat.lower()} purchases for the remainder of the month to prevent further budget deficit."
        priorities = [
            f"Rebalance budget for {ov_cat}",
            "Review transactions from the past 7 days",
            "Protect your monthly savings target"
        ]
        reply = f"""### ⚠️ Budget Alert: {ov_cat}

- **Over budget by**: **₹{ov_amt:,.0f}**
- **Current Savings Rate**: **{savings_rate:.1f}%**
- **Total Income**: ₹{income:,.0f} | **Total Expenses**: ₹{total_exp:,.0f}{goals_note_overview}

**Recommendation**: {recommendation}"""
    else:
        summary = f"Highest spending category: {top_cat[0]} (₹{top_cat[1]:,.0f}). Monthly savings rate: {savings_rate:.1f}%."
        recommendation = "Keep essential spending steady and route surplus funds toward your active savings goals and emergency reserves."
        priorities = [
            f"Review {top_cat[0]} transactions this week",
            f"Allocate ₹{total_monthly_goal_need:,.0f}/mo towards your goals" if total_monthly_goal_need > 0 else "Maintain your 20%+ savings cushion",
            "Contribute to your active savings goals"
        ]
        reply = f"""### 🌟 Financial Health Snapshot

- **Monthly Income**: **₹{income:,.0f}**
- **Monthly Expenses**: **₹{total_exp:,.0f}**
- **Net Savings**: **₹{ctx['total_savings']:,.0f}** (Savings Rate: **{savings_rate:.1f}%**)
- **Top Expense Category**: **{top_cat[0]}** (₹{top_cat[1]:,.0f}){goals_note_overview}

**Status**: {'🎉 Great job maintaining a healthy savings rate!' if savings_rate >= 20 else '💡 Look for opportunities to trim non-essentials to reach a 20% savings rate.'}"""

    return {
        "summary": summary,
        "recommendation": recommendation,
        "priorities": priorities,
        "reply": reply,
        "source": "Intelligent Financial Advisor Engine"
    }


def analyze(user, metrics, question=None, history=None):
    """
    Main AI advisory entrypoint.
    First attempts to use Google Gemini 2.0 / 1.5 Flash if GEMINI_API_KEY is configured.
    Gracefully falls back to the smart local financial advisor engine if key is absent or API fails.
    """
    expected_user_id = str(user.get_id())
    api_key = (current_app.config.get("GEMINI_API_KEY") or "").strip()
    
    fallback = smart_local_financial_advisor(user, metrics, question)
    
    if not api_key:
        return fallback

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        
        ctx = get_user_financial_context(user, metrics)
        if ctx.get("user_id") != expected_user_id:
            raise RuntimeError("Refusing to send financial context for a different user")
        
        system_instruction = (
            "You are PaisaPath AI's Personal Financial Advisor Chatbot. "
            "You provide practical, encouraging, educational budgeting and personal finance guidance strictly grounded in the user's provided financial data. "
            "Never recommend specific individual stocks, crypto, or licensed securities. "
            "Always reference their exact numbers (in ₹ INR) when relevant. "
            "IMPORTANT: When advising the user (especially on savings, budgeting, expense cuts, or when asked about goals/milestones), "
            "you MUST actively discuss their specific Active Goals (e.g. name, target date, remaining balance, and required monthly savings ₹/month). "
            "Explicitly calculate and show how trimming discretionary spending or reallocating budget enables them to hit their monthly goal savings target on schedule. "
            "Return a valid JSON object with the following fields:\n"
            "- 'summary': A concise 1-2 sentence overview\n"
            "- 'recommendation': Specific actionable guidance addressing their query, goals, and spending\n"
            "- 'priorities': An array of 3-4 short, clear action items\n"
            "- 'reply': A comprehensive, well-formatted markdown response to the user's question, including tables or bullet lists where appropriate."
        )
        
        user_prompt = f"""User Profile:
- Name: {ctx['user_name']}
- User Type: {ctx['user_type']}
- Stated Monthly Income Preference: ₹{ctx['monthly_income']:,.0f}
- Recorded Monthly Income: ₹{ctx['recorded_income']:,.0f}
- Recorded Total Expenses: ₹{ctx['total_expenses']:,.0f}
- Net Monthly Savings: ₹{ctx['total_savings']:,.0f} (Savings Rate: {ctx['savings_rate']:.1f}%)
- Monthly Savings Target: ₹{ctx['savings_target']:,.0f}
- Financial Goal Note: {ctx['financial_goal']}

Category Expenses:
{json.dumps(ctx['category_expenses'], indent=2)}

Essential Spending: ₹{ctx['essential_spending']:,.0f}
Discretionary Spending: ₹{ctx['discretionary_spending']:,.0f}
Overspending vs Budget: {json.dumps(ctx['overspending'])}
Active Goals (including Target Dates and Monthly Savings Needed):
{json.dumps(ctx['goals'], indent=2)}
Recent Transactions: {json.dumps(ctx['recent_expenses'][:5])}

User Question / Request: "{question or 'Provide a comprehensive monthly financial analysis, active goals progress with target dates and required monthly savings, and actionable savings advice.'}"
"""

        candidate_models = [
            "gemini-3.5-flash-lite",
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-flash-lite-latest",
            "gemini-flash-latest",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-pro-latest"
        ]
        response = None
        model_name = None
        for m in candidate_models:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=[system_instruction, user_prompt]
                )
                model_name = m
                break
            except Exception as e:
                continue

        if not response or not model_name:
            return fallback

        text = response.text.strip()
        # Clean markdown code blocks if wrapped
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        result = json.loads(text)
        
        reply_content = result.get("reply") or result.get("recommendation") or fallback["reply"]
        
        return {
            "summary": str(result.get("summary", fallback["summary"])),
            "recommendation": str(result.get("recommendation", fallback["recommendation"])),
            "priorities": result.get("priorities", fallback["priorities"]),
            "reply": str(reply_content),
            "source": f"Google Gemini AI ({model_name})"
        }
    except Exception as exc:
        print(f"[AI Service] Gemini call failed, using intelligent advisor fallback: {exc}")
        return fallback

