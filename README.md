# Personal Finance Advisor Bot

A runnable Flask + SQLite personal finance workspace for tracking income, expenses, budgets, goals, reports, and AI-assisted educational insights. The deterministic Python financial engine calculates totals, savings, category spending, budget utilization, and trends before Gemini is asked to explain them.

## Features

- Secure registration, login, password hashing, and per-user data isolation
- Income and expense recording with validation, editing, and deletion
- Monthly budgets with history-aware suggested allocations
- Savings goals with progress and contributions
- Financial Report charts backed by current database data
- Printable monthly reports
- Gemini integration through a backend service with a rule-based fallback
- PostgreSQL-ready SQLAlchemy configuration through `DATABASE_URL`
- Responsive fintech UI and friendly error pages

## Run locally

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Open `http://127.0.0.1:5000`. The SQLite database is created in `instance/finance.db` on first startup.

Set a strong `FLASK_SECRET_KEY` in `.env`. Set `GEMINI_API_KEY` to enable Gemini analysis; leaving it blank keeps the application fully usable with deterministic fallback guidance. SQLite is the default. For PostgreSQL, set `DATABASE_URL` to a URL such as `postgresql+psycopg://user:password@localhost:5432/finance`.

## Demo data

```powershell
python seed.py
```

This creates `demo@example.com` with password `DemoPass123!` and a small sample dataset. This credential is for local demonstration only.

## Tests

```powershell
python -m pytest -q
```

The suite covers registration and login, protected routes, income and expense calculations, budget generation, goal contributions, AI fallback availability, and cross-user data isolation.

## Ngrok

Start the app with `python app.py`, then in another terminal run:

```powershell
ngrok http 5000
```

Use the generated HTTPS URL for your demonstration. No public URL is hardcoded.

## Architecture

`app.py` creates the Flask app and database tables. `models/` contains SQLAlchemy entities. `routes/` owns request handling and user ownership filters. `services/financial_engine.py` and `services/budget_engine.py` perform deterministic calculations. `services/ai_service.py` receives structured metrics and falls back safely when Gemini is unavailable. Templates and CSS provide the responsive interface.

## Safety

This application provides educational budgeting and financial planning insights and is not a substitute for professional financial advice. It does not recommend securities or promise returns. Never commit `.env`, production credentials, or the demo password to a public deployment.
