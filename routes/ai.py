from flask import Blueprint, jsonify, render_template, request, session, flash, redirect, url_for
from flask_login import current_user, login_required
from extensions import db
from models import ChatMessage
from services.ai_service import analyze
from services.financial_engine import monthly_metrics

aI_bp = Blueprint("ai", __name__)


def _chat_history_key(user_id):
    """Keep transient conversations isolated even if a session is reused."""
    return f"chat_history:{user_id}"


def _history_for_current_user():
    key = _chat_history_key(current_user.id)
    if key not in session:
        session[key] = [
            {"role": message.role, "content": message.content}
            for message in ChatMessage.query.filter_by(user_id=current_user.id).order_by(ChatMessage.id).all()
        ][-8:]
    return session.get(key, [])


def _store_history(history):
    session[_chat_history_key(current_user.id)] = history[-8:]
    session.modified = True

def _persist_message(role, content):
    db.session.add(ChatMessage(user_id=current_user.id, role=role, content=content))
    db.session.commit()


@aI_bp.route("/ai-advisor", methods=["GET", "POST"])
@login_required
def advisor():
    metrics = monthly_metrics(current_user.id)
    history = _history_for_current_user()
    
    question = ""
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        answer = analyze(current_user, metrics, question)
        if question:
            _persist_message("user", question)
            _persist_message("assistant", answer.get("reply", answer.get("recommendation", "")))
            history.append({"role": "user", "content": question})
            history.append({
                "role": "assistant",
                "content": answer.get("reply", answer.get("recommendation", "")),
                "summary": answer.get("summary"),
                "recommendation": answer.get("recommendation"),
                "priorities": answer.get("priorities", []),
                "source": answer.get("source", "Intelligent Financial Advisor Engine")
            })
            _store_history(history)
    else:
        # Default analysis when opening the page
        answer = analyze(current_user, metrics, "Give a monthly financial analysis and savings overview.")
        if not history:
            history.append({
                "role": "assistant",
                "content": answer.get("reply", answer.get("recommendation", "")),
                "summary": answer.get("summary"),
                "recommendation": answer.get("recommendation"),
                "priorities": answer.get("priorities", []),
                "source": answer.get("source", "Intelligent Financial Advisor Engine")
            })
            _store_history(history)

    return render_template(
        "ai_advisor.html", 
        answer=answer, 
        question=question, 
        metrics=metrics, 
        chat_history=_history_for_current_user()
    )


@aI_bp.post("/ai-advisor/chat")
@aI_bp.post("/ai-advisor/analyze")
@login_required
def chat_api():
    if request.is_json:
        data = request.get_json() or {}
        question = data.get("question", "").strip()
    else:
        question = request.form.get("question", "").strip()

    metrics = monthly_metrics(current_user.id)
    answer = analyze(current_user, metrics, question)
    
    history = _history_for_current_user()
    if question:
        _persist_message("user", question)
        history.append({"role": "user", "content": question})
    
    msg = {
        "role": "assistant",
        "content": answer.get("reply", answer.get("recommendation", "")),
        "summary": answer.get("summary"),
        "recommendation": answer.get("recommendation"),
        "priorities": answer.get("priorities", []),
        "source": answer.get("source", "Intelligent Financial Advisor Engine")
    }
    _persist_message("assistant", msg["content"])
    history.append(msg)
    _store_history(history)

    if request.is_json or request.headers.get("Accept") == "application/json":
        return jsonify({
            "success": True,
            "answer": answer,
            "message": msg
        })
    
    return render_template(
        "ai_advisor.html", 
        answer=answer, 
        question=question, 
        metrics=metrics, 
        chat_history=_history_for_current_user()
    )


@aI_bp.post("/ai-advisor/clear")
@login_required
def clear_history():
    _store_history([])
    if request.is_json:
        return jsonify({"success": True})
    flash("Conversation cleared.", "info")
    return redirect(url_for("ai.advisor"))


