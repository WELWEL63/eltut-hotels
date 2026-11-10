"""
blueprints/public/chat_routes.py
────────────────────────────────
API endpoints for the floating chat widget.

ROUTES
    POST /api/chat/start        - Creates a new session or returns active
    POST /api/chat/message      - Receives user message, returns bot reply
    POST /api/chat/human        - Escalates session to a human
    GET  /api/chat/poll/<id>    - Polls for new messages (used for human handover)

DESIGN
    - Pure JSON responses. No HTML rendering.
    - Uses `mongo.chat` for storage and `services.chatbot_service` for logic.
    - Includes a simple polling endpoint so the frontend can fetch human replies
      without needing WebSockets (SocketIO).
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
    """Start a chat session or retrieve the existing active one."""
    user_id = current_user.id if current_user.is_authenticated else None
    guest_name = current_user.full_name if current_user.is_authenticated else "Guest"
    
    # Try to find an existing session
    session = chat_repo.get_active_session(user_id=user_id)
    
    if not session:
        session = chat_repo.create_session(user_id=user_id, guest_name=guest_name)
        # Send initial greeting
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

    try:
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

    try:
        result = chatbot_service.trigger_human_handover(session_id)
        return jsonify({"ok": True, "result": result})
    except Exception as exc:
        log.error("Human handover failed: %s", exc)
        return jsonify({"ok": False, "error": "Failed to escalate"}), 500


@public_bp.route("/api/chat/poll/<session_id>", methods=["GET"])
@limiter.exempt
def api_chat_poll(session_id):
    """
    Poll for new messages.
    The frontend sends the timestamp of the last message it received,
    and we return anything newer.
    """
    since_str = request.args.get("since")
    
    try:
        # In a real production app, we would filter by `since`.
        # For simplicity in this coursework version, we just return the last 50 messages.
        # The frontend will handle only appending the new ones.
        messages = chat_repo.get_messages(session_id, limit=50)
        session = chat_repo.get_session(session_id)
        
        if not session:
            return jsonify({"ok": False, "error": "Session not found"}), 404

        return jsonify({
            "ok": True, 
            "messages": messages,
            "status": session["status"]
        })
    except Exception as exc:
        log.error("Chat poll failed: %s", exc)
        return jsonify({"ok": False, "error": "Failed to poll"}), 500