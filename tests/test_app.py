from datetime import date, timedelta
import pytest
from app import create_app
from extensions import db
from models import Budget, Expense, Goal, User

today = date.today()
cur_m_1 = today.replace(day=1).strftime("%Y-%m-%d")
cur_m_2 = today.replace(day=2).strftime("%Y-%m-%d")
cur_m_3 = today.replace(day=3).strftime("%Y-%m-%d")
cur_m_4 = today.replace(day=4).strftime("%Y-%m-%d")
last_m_2 = (today.replace(day=1) - timedelta(days=1)).replace(day=2).strftime("%Y-%m-%d")

@pytest.fixture
def client():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "WTF_CSRF_ENABLED": False, "GEMINI_API_KEY": ""})
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()
        yield client

def register(client, email="a@example.com"):
    client.get("/logout")
    client.post("/register", data={"name":"A User", "email":email, "password":"Password123", "confirm_password":"Password123", "user_type":"Student"}, follow_redirects=True)
    return client.post("/login", data={"email": email, "password": "Password123"}, follow_redirects=True)

def test_registration_login_and_protected_reports(client):
    response = register(client)
    assert b"Financial Snapshot" in response.data or b"Financial report" in response.data
    client.get("/logout")
    assert b"Financial Snapshot" in client.post("/login", data={"email":"a@example.com", "password":"Password123"}, follow_redirects=True).data or b"Financial report" in client.post("/login", data={"email":"a@example.com", "password":"Password123"}, follow_redirects=True).data

def test_landing_navigation_tracks_flask_login_state(client):
    public_page = client.get("/")
    assert b">Log in<" in public_page.data
    assert b">Reports<" not in public_page.data

    register(client)
    authenticated_page = client.get("/")
    assert b">Reports<" in authenticated_page.data
    assert b">Profile<" in authenticated_page.data
    assert b">Log out<" in authenticated_page.data
    assert b">Log in<" not in authenticated_page.data

    client.get("/logout")
    logged_out_page = client.get("/")
    assert b">Log in<" in logged_out_page.data
    assert b">Reports<" not in logged_out_page.data

def test_paisapath_branding_is_shared_across_pages(client):
    old_brand = "Fin" + "Pilot"
    legacy_brand = "Ledger" + "ly"
    theme_control = "theme" + "Toggle"
    theme_storage = "paisapath-" + "theme"
    public_page = client.get("/").data.decode("utf-8")
    assert "PaisaPath AI" in public_page
    assert theme_control not in public_page
    assert theme_storage not in public_page
    assert old_brand not in public_page
    assert legacy_brand not in public_page

    register(client)
    for path in ("/reports", "/ai-advisor", "/profile"):
        page = client.get(path).data.decode("utf-8")
        assert "PaisaPath AI" in page
        assert theme_control not in page
        assert theme_storage not in page
        assert old_brand not in page
        assert legacy_brand not in page

def test_profile_hides_gemini_configuration_and_keeps_profile_updates(client):
    register(client)

    profile = client.get("/profile")
    assert profile.status_code == 200
    profile_html = profile.data.decode("utf-8")
    for forbidden in ("gemini_api_key", "Google Gemini AI Configuration", "Gemini 2.0 Active", "Google AI Studio", "••••••••••"):
        assert forbidden not in profile_html

    update = client.post("/profile", data={
        "name": "Updated User",
        "user_type": "Freelancer",
        "monthly_income": "42000",
        "savings_target": "12000",
        "financial_goal": "Build an emergency fund",
    })
    assert update.status_code == 302
    assert b"Updated User" in client.get("/profile").data

    ai_page = client.get("/ai-advisor")
    ai_html = ai_page.data.decode("utf-8")
    for forbidden in ("gemini_api_key", "Gemini 2.0 Active", "Google AI Studio", "apiKeyModal"):
        assert forbidden not in ai_html

    chat_response = client.post("/ai-advisor/chat", json={"question": "Give me a savings overview"})
    assert chat_response.status_code == 200
    assert "has_gemini" not in chat_response.get_json()

def test_finance_records_update_reports(client):
    register(client)
    client.post("/income", data={"amount":"30000", "source":"Salary", "date":cur_m_1})
    client.post("/expenses", data={"amount":"5000", "category":"Food", "date":cur_m_2, "payment_method":"UPI"})
    report = client.get("/reports")
    assert b"25,000" in report.data
    assert b"Food" in report.data

def test_reports_filters_transactions_and_exports_calculated_data(client):
    register(client)
    client.post("/income", data={"amount": "50000", "source": "Salary", "date": cur_m_1})
    client.post("/expenses", data={"amount": "12000", "category": "Rent", "date": cur_m_2, "payment_method": "UPI"})
    client.post("/expenses", data={"amount": "3000", "category": "Shopping", "date": last_m_2, "payment_method": "Cash"})

    report = client.get("/reports?preset=this_month")
    assert report.status_code == 200
    report_html = report.data.decode("utf-8")
    assert "Financial report" in report_html
    assert "Income vs expenses" in report_html
    assert "Expense breakdown" in report_html
    assert "GOAL PROGRESS" in report_html
    assert "Budget vs actual" in report_html
    assert "FINANCIAL SUMMARY" in report_html
    assert "KEY INSIGHTS" in report_html
    assert 'id="reportCashFlowChart"' in report_html
    assert 'id="reportCategoryChart"' in report_html
    assert "Over budget by" not in report_html
    assert "Rent" in report_html
    assert "Shopping" not in report_html

    filtered = client.get("/expenses?category=Rent&sort=highest")
    assert b"Rent" in filtered.data
    assert b"12,000.00" in filtered.data
    assert b"3,000.00" not in filtered.data

    exported = client.get("/reports/export.csv?preset=this_month")
    assert exported.status_code == 200
    assert b"Income,50000.0" in exported.data
    assert b"Rent,12000.0" in exported.data

    transactions = client.get("/transactions/export.csv?type=expense&category=Rent")
    assert transactions.status_code == 200
    assert b"Rent" in transactions.data
    assert b"Shopping" not in transactions.data

def test_empty_report_has_meaningful_chart_states(client):
    register(client)
    report = client.get("/reports?preset=this_month")
    report_html = report.data.decode("utf-8")
    assert "No historical data available yet." in report_html
    assert "No expense data available yet." in report_html
    assert "No budget data available yet." in report_html
    assert "No active goals yet." in report_html

def test_routes_require_login(client):
    assert client.get("/dashboard").status_code == 404
    assert client.get("/snapshot").status_code == 302
    assert client.get("/financial-snapshot").status_code == 302
    assert client.get("/reports").status_code == 302
    assert client.get("/expenses").status_code == 302

def test_budget_generation_goal_contribution_and_ai_fallback(client):
    register(client)
    client.post("/income", data={"amount":"30000", "source":"Salary", "date":cur_m_1})
    response = client.post("/budget/generate", follow_redirects=True)
    assert response.status_code == 200
    with client.application.app_context():
        assert Budget.query.count() > 0
        goal = Goal(user_id=1, name="Laptop", target_amount=1000, current_amount=100, target_date=__import__("datetime").date.today())
        db.session.add(goal)
        db.session.commit()
        goal_id = goal.id
    client.post(f"/goals/contribute/{goal_id}", data={"amount":"250"})
    assert b"AI Advisor" in client.get("/ai-advisor").data
    with client.application.app_context():
        assert db.session.get(Goal, goal_id).current_amount == 350

def test_user_data_isolation(client):
    register(client, "first@example.com")
    client.post("/expenses", data={"amount":"500", "category":"Food", "date":cur_m_2, "payment_method":"Cash"})
    with client.application.app_context():
        expense_id = Expense.query.filter_by(amount=500).first().id
    client.get("/logout")
    register(client, "second@example.com")
    assert b"500" not in client.get("/expenses").data
    assert client.post(f"/expenses/delete/{expense_id}").status_code == 404


def test_ai_chat_history_isolated_across_account_switches(client):
    register(client, "first@example.com")
    client.post("/ai-advisor/chat", json={"question": "first account private question"})
    assert b"first account private question" in client.get("/ai-advisor").data

    client.get("/logout")
    register(client, "second@example.com")
    second_page = client.get("/ai-advisor").data
    assert b"first account private question" not in second_page

    client.get("/logout")
    client.post("/login", data={"email": "first@example.com", "password": "Password123"})
    assert b"first account private question" in client.get("/ai-advisor").data


def test_financial_and_ai_context_isolated_a_to_b_to_a(client):
    register(client, "owner-a@example.com")
    client.post("/income", data={"amount": "50000", "source": "Salary", "date": cur_m_1})
    client.post("/expenses", data={"amount": "30000", "category": "Rent", "date": cur_m_2, "payment_method": "UPI"})
    client.post("/goals", data={"name": "Laptop Private Goal", "target_amount": "80000", "current_amount": "10000"})
    assert b"50,000" in client.get("/reports").data
    ai_a = client.post("/ai-advisor/chat", json={"question": "how much should I save per month for my goals?"}).data
    assert b"Laptop Private Goal" in ai_a

    client.get("/logout")
    register(client, "owner-b@example.com")
    reports_b = client.get("/reports").data
    ai_b = client.post("/ai-advisor/chat", json={"question": "Give me my financial overview"}).data
    assert b"50,000" not in reports_b
    assert b"30,000" not in reports_b
    assert b"Laptop Private Goal" not in reports_b
    assert b"50,000" not in ai_b
    assert b"30,000" not in ai_b
    assert b"Laptop Private Goal" not in ai_b

    client.get("/logout")
    client.post("/login", data={"email": "owner-a@example.com", "password": "Password123"})
    assert b"50,000" in client.get("/reports").data
    assert b"Laptop Private Goal" in client.post("/ai-advisor/chat", json={"question": "how much should I save per month for my goals?"}).data

def test_expenses_and_income_page_dropdown_options(client):
    register(client)
    expenses_page = client.get("/expenses").data.decode("utf-8")
    assert "<option>Food</option>" in expenses_page
    assert "<option>Rent</option>" in expenses_page
    assert "<option>Transport</option>" in expenses_page

    income_page = client.get("/income").data.decode("utf-8")
    assert "<option>Salary</option>" in income_page
    assert "<option>Freelance</option>" in income_page

def test_income_filters_are_embedded_once_in_summary_card(client):
    register(client)
    client.post("/income", data={"amount": "53000", "source": "Salary", "date": cur_m_1, "description": "Monthly salary"})
    income_page = client.get("/income").data.decode("utf-8")
    assert income_page.count("FIND A RECORD") == 1
    assert income_page.index("ALL TIME IN THIS VIEW") < income_page.index("FIND A RECORD") < income_page.index("Recent records")

    filtered = client.get("/income?source=Salary&sort=highest")
    assert b"Monthly salary" in filtered.data
    exported = client.get("/transactions/export.csv?type=income&source=Salary")
    assert exported.status_code == 200
    assert b"Monthly salary" in exported.data

def test_ai_chatbot_interactive_qa_and_api(client):
    register(client)
    # Add expenses across categories
    client.post("/income", data={"amount":"50000", "source":"Salary", "date":cur_m_1})
    client.post("/expenses", data={"amount":"15000", "category":"Rent", "date":cur_m_2, "payment_method":"UPI"})
    client.post("/expenses", data={"amount":"7000", "category":"Shopping", "date":cur_m_3, "payment_method":"Credit Card"})
    client.post("/expenses", data={"amount":"5000", "category":"Food", "date":cur_m_4, "payment_method":"UPI"})

    # Test traditional form submit
    resp = client.post("/ai-advisor", data={"question":"where can I save my money ?"}, follow_redirects=True)
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "Savings Breakdown" in html or "Shopping" in html

    # Test JSON AJAX Chatbot API
    json_resp = client.post("/ai-advisor/chat", json={"question": "where dose i can save my money ?"})
    assert json_resp.status_code == 200
    data = json_resp.get_json()
    assert data["success"] is True
    assert "answer" in data
    assert len(data["answer"]["priorities"]) > 0
    assert "Shopping" in data["answer"]["reply"] or "save" in data["answer"]["reply"].lower()

    # Test 50/30/20 budget check
    json_resp_50 = client.post("/ai-advisor/chat", json={"question": "calculate 50/30/20 rule"})
    assert json_resp_50.status_code == 200
    data_50 = json_resp_50.get_json()
    assert "50/30/20" in data_50["answer"]["reply"]


def test_goal_target_date_monthly_savings_and_ai_integration(client):
    register(client, "goals_user@example.com")
    client.post("/income", data={"amount": "100000", "source": "Salary", "date": cur_m_1})
    
    # Create a goal with future target date
    future_date = "2027-09-01"
    client.post("/goals", data={
        "name": "Flat in Ecocity",
        "target_amount": "2500000",
        "current_amount": "1500000",
        "target_date": future_date,
        "description": "2 BHK Flat down payment"
    }, follow_redirects=True)
    
    # Check goals page rendering
    goals_page = client.get("/goals").data.decode("utf-8")
    assert "Flat in Ecocity" in goals_page
    assert "Target:" in goals_page or "Target Date" in goals_page
    assert "REQUIRED MONTHLY SAVINGS" in goals_page
    
    # Check report rendering
    report_page = client.get("/reports").data.decode("utf-8")
    assert "Flat in Ecocity" in report_page
    assert "Required monthly" in report_page
    
    # Check AI Advisor discussion about goals
    ai_resp = client.post("/ai-advisor/chat", json={"question": "how much should I save per month for my goals?"})
    assert ai_resp.status_code == 200
    data = ai_resp.get_json()
    assert data["success"] is True
    reply = data["answer"]["reply"]
    assert "Flat in Ecocity" in reply or "Goal" in reply
    assert "month" in reply.lower()


def test_financial_snapshot_dashboard_and_filtering(client):
    assert client.get("/snapshot").status_code == 302
    assert client.get("/financial-snapshot").status_code == 302

    login_resp = register(client, "snapshot-test@example.com")
    assert login_resp.status_code == 200
    assert b"Financial Snapshot" in login_resp.data

    client.post("/income", data={"amount": "60000", "source": "Salary", "date": cur_m_1, "description": "Tech Salary"})
    client.post("/expenses", data={"amount": "15000", "category": "Rent", "date": cur_m_2, "payment_method": "UPI", "description": "Apartment Rent"})
    client.post("/expenses", data={"amount": "5000", "category": "Food", "date": cur_m_3, "payment_method": "UPI", "description": "Groceries"})
    client.post("/goals", data={"name": "Emergency Fund", "target_amount": "100000", "current_amount": "25000"})

    page = client.get("/snapshot")
    assert page.status_code == 200
    html = page.data.decode("utf-8")
    assert "Financial Snapshot" in html
    assert "Total Balance" in html
    assert "Income" in html
    assert "Expenses" in html
    assert "Net Savings" in html
    assert "Monthly Trend" in html
    assert "Spending by Category" in html
    assert "Your Financial Health" in html
    assert "Recent Transactions" in html
    assert "Financial Goals" in html
    assert "AI Financial Insight" in html
    assert "Tech Salary" in html
    assert "Apartment Rent" in html

    filtered = client.get("/snapshot?preset=last_month")
    assert filtered.status_code == 200
    assert "Savings Rate" in html
    assert "Cash Flow" in html
    assert "Savings Trend" in html

    # Verify adding a transaction updates snapshot
    client.post("/expenses", data={"amount": "2000", "category": "Transport", "date": cur_m_4, "payment_method": "Cash", "description": "Metro Pass"})
    updated_page = client.get("/snapshot")
    assert b"Metro Pass" in updated_page.data
    assert b"Transport" in updated_page.data

