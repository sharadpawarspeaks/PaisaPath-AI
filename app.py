import os
from pathlib import Path
from datetime import date, datetime

from flask import Flask, render_template, session
from sqlalchemy import inspect, text

from config import Config
from models import db, login_manager


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)

    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(User, int(user_id))
        session_version = session.get("auth_version")
        if user and (session_version is None or session_version != user.auth_version):
            return None
        return user

    from routes.auth import auth_bp
    from routes.main import main_bp
    from routes.finance import finance_bp
    from routes.ai import aI_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(aI_bp)

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    @app.context_processor
    def inject_globals():
        return {"today": datetime.now(), "now": datetime.now()}

    with app.app_context():
        db.create_all()
        user_columns = {column["name"] for column in inspect(db.engine).get_columns("user")}
        for column_name, definition in {
            "email_verified": "BOOLEAN NOT NULL DEFAULT 1",
            "otp_hash": "VARCHAR(255)",
            "otp_expires_at": "DATETIME",
            "otp_attempts": "INTEGER NOT NULL DEFAULT 0",
            "otp_created_at": "DATETIME",
            "otp_purpose": "VARCHAR(30)",
            "auth_version": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if column_name not in user_columns:
                db.session.execute(text(f"ALTER TABLE user ADD COLUMN {column_name} {definition}"))
                db.session.commit()
        if "annual_increase_percent" not in {column["name"] for column in inspect(db.engine).get_columns("income")}:
            db.session.execute(text("ALTER TABLE income ADD COLUMN annual_increase_percent FLOAT NOT NULL DEFAULT 0"))
            db.session.commit()
        if "annual_increase_effective_date" not in {column["name"] for column in inspect(db.engine).get_columns("income")}:
            db.session.execute(text("ALTER TABLE income ADD COLUMN annual_increase_effective_date DATE"))
            db.session.commit()
        income_columns = {column["name"] for column in inspect(db.engine).get_columns("income")}
        for column_name, definition in {
            "frequency": "VARCHAR(20) NOT NULL DEFAULT 'Monthly'",
            "recurring": "BOOLEAN NOT NULL DEFAULT 1",
            "end_date": "DATE",
        }.items():
            if column_name not in income_columns:
                db.session.execute(text(f"ALTER TABLE income ADD COLUMN {column_name} {definition}"))
                db.session.commit()
        goal_columns = inspect(db.engine).get_columns("goal")
        target_column = next((column for column in goal_columns if column["name"] == "target_date"), None)
        if target_column and not target_column.get("nullable", True) and db.engine.dialect.name == "sqlite":
            db.session.execute(text("PRAGMA foreign_keys=OFF"))
            db.session.execute(text("ALTER TABLE goal RENAME TO goal_legacy"))
            db.session.execute(text("CREATE TABLE goal (id INTEGER NOT NULL PRIMARY KEY, user_id INTEGER NOT NULL, name VARCHAR(120) NOT NULL, target_amount FLOAT NOT NULL, current_amount FLOAT NOT NULL, target_date DATE, description VARCHAR(255), created_at DATETIME, FOREIGN KEY(user_id) REFERENCES user (id))"))
            db.session.execute(text("INSERT INTO goal (id, user_id, name, target_amount, current_amount, target_date, description, created_at) SELECT id, user_id, name, target_amount, current_amount, target_date, description, created_at FROM goal_legacy"))
            db.session.execute(text("DROP TABLE goal_legacy"))
            db.session.execute(text("CREATE INDEX ix_goal_user_id ON goal (user_id)"))
            db.session.execute(text("PRAGMA foreign_keys=ON"))
            db.session.commit()
        expense_columns = {column["name"] for column in inspect(db.engine).get_columns("expense")}
        for column_name, definition in {
            "frequency": "VARCHAR(20) NOT NULL DEFAULT 'Monthly'",
            "recurring": "BOOLEAN NOT NULL DEFAULT 1",
            "end_date": "DATE",
        }.items():
            if column_name not in expense_columns:
                db.session.execute(text(f"ALTER TABLE expense ADD COLUMN {column_name} {definition}"))
                db.session.commit()
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
