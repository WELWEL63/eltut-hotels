"""
blueprints/public/chat_routes.py
────────────────────────────────
API endpoints for the floating chat widget.

Design:
- Admin closes a human chat → user stays with the bot, but the chat
  is no longer visible to the admin.
- Guest sessions are strictly isolated by session_id.
- On tab close, /api/chat/end deletes the session.
"""

from __future__ import annotations

import logging
from flask import jsonify, request
from flask_login import current_user

from blueprints.public import public_bp
from mongo import chat as chat_repo
from services import chatbot_service
from extensions import csrf, limiter

log = logging.getLogger(__name__)


@public_bp.route("/api/chat/start", methods=["POST"])
@csrf.exempt
@limiter.exempt
def api_chat_start():
    """Start a session, or resume if the exact ID is provided and open."""
    user_id = current_user.id if current_user.is_authenticated else None
    guest_name = current_user.full_name if current_user.is_authenticated else "Guest"

    data = request.get_json(silent=True) or {}
    client_session_id = data.get("session_id")

    session = chat_repo.get_active_session(
        user_id=user_id,
        session_id=client_session_id,
    )

    if not session:
        session = chat_repo.create_session(user_id=user_id, guest_name=guest_name)
        chat_repo.add_message(session["id"], "bot", chatbot_service.GREETING_MSG)

    return jsonify({"ok": True, "session": session})


@public_bp.route("/api/chat/message", methods=["POST"])
@csrf.exempt
@limiter.exempt
def api_chat_message():
    """Receive a user message and process it through the bot."""
    data = request.get_json() or {}
    session_id = data.get("session_id")
    text = (data.get("text") or "").strip()

    if not session_id or not text:
        return jsonify({"ok": False, "error": "Missing session_id or text"}), 400

    # If the session was deleted (tab was closed & user returned via stale link),
    # give them a fresh one. Otherwise, ALWAYS allow — including 'closed' sessions,
    # so the bot keeps answering after the admin ends the human handover.
    session = chat_repo.get_session(session_id)
    if not session:
        return jsonify({"ok": False, "error": "Session not found", "restart": True}), 404

    try:
        # If the admin had closed the human chat, downgrade back to bot mode
        # so the user can keep chatting with the bot as a fresh bot session.
        if session["status"] == chat_repo.SESSION_STATUS_CLOSED:
            chat_repo.update_session_status(session_id, chat_repo.SESSION_STATUS_BOT)

        result = chatbot_service.process_user_message(session_id, text)
        return jsonify({"ok": True, "result": result})
    except Exception as exc:
        log.error("Chat message failed: %s", exc)
        return jsonify({"ok": False, "error": "Failed to process message"}), 500


@public_bp.route("/api/chat/human", methods=["POST"])
@csrf.exempt
@limiter.exempt
def api_chat_human():
    """Escalate the chat to a human agent."""
    data = request.get_json() or {}
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({"ok": False, "error": "Missing session_id"}), 400

    session = chat_repo.get_session(session_id)
    if not session:
        return jsonify({"ok": False, "error": "Session not found", "restart": True}), 404

    try:
        result = chatbot_service.trigger_human_handover(session_id)
        return jsonify({"ok": True, "result": result})
    except Exception as exc:
        log.error("Human handover failed: %s", exc)
        return jsonify({"ok": False, "error": "Failed to escalate"}), 500


@public_bp.route("/api/chat/poll/<session_id>", methods=["GET"])
@limiter.exempt
def api_chat_poll(session_id):
    """Poll for new messages."""
    try:
        messages = chat_repo.get_messages(session_id, limit=50)
        session = chat_repo.get_session(session_id)

        if not session:
            return jsonify({"ok": False, "error": "Session not found", "restart": True}), 404

        # IMPORTANT: if status is 'closed', the widget should reset the status
        # label to "bot mode" but NOT force a new session — the user can keep
        # chatting with the bot in the same session.
        return jsonify({
            "ok": True,
            "messages": messages,
            "status": session["status"],
        })
    except Exception as exc:
        log.error("Chat poll failed: %s", exc)
        return jsonify({"ok": False, "error": "Failed to poll"}), 500


@public_bp.route("/api/chat/end", methods=["POST"])
@csrf.exempt
@limiter.exempt
def api_chat_end():
    """Called via sendBeacon when the user closes the tab / navigates away."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    if session_id:
        try:
            chat_repo.delete_session(session_id)
        except Exception as exc:
            log.error("Chat delete failed: %s", exc)
    return jsonify({"ok": True})