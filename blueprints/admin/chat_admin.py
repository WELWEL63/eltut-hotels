"""
blueprints/admin/chat_admin.py
──────────────────────────────
Admin routes for handling live chat support.

ROUTES
    GET  /admin/chat              - List active and waiting chats
    GET  /admin/chat?session_id=  - View a specific chat session (in split panel)
    POST /admin/chat/<id>/reply   - Send a reply to the user
    POST /admin/chat/<id>/close   - Close the chat session
"""

from __future__ import annotations

import logging
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import current_user

from blueprints.admin import admin_bp
from mongo import chat as chat_repo
from extensions import csrf

log = logging.getLogger(__name__)


@admin_bp.route("/chat")
def chat_list():
    """Show all waiting and active human sessions."""
    waiting = chat_repo.list_sessions_waiting_for_human(limit=20)
    active = chat_repo.list_active_human_sessions(limit=20)

    # Check if an admin clicked a specific session (via ?session_id=...)
    session_id = request.args.get("session_id")
    current_session = None
    messages = []

    if session_id:
        current_session = chat_repo.get_session(session_id)
        if current_session:
            # If the admin opens a waiting chat, automatically mark it as 'human'
            # so the bot stops replying and the user knows an agent is there.
            if current_session["status"] == chat_repo.SESSION_STATUS_WAITING:
                chat_repo.update_session_status(session_id, chat_repo.SESSION_STATUS_HUMAN)
                chat_repo.add_message(
                    session_id,
                    "system",
                    f"Agent {current_user.full_name} joined the chat.",
                    sender_name="System",
                )
                current_session = chat_repo.get_session(session_id)  # Refresh

            messages = chat_repo.get_messages(session_id, limit=100)

    return render_template(
        "admin/chat_dashboard.html",
        waiting=waiting,
        active=active,
        current_session=current_session,
        messages=messages,
        page="chat",
    )


@admin_bp.route("/chat/<session_id>")
def chat_detail(session_id: str):
    """Legacy detail route — now redirects to the split view."""
    return redirect(url_for("admin.chat_list", session_id=session_id))


@admin_bp.route("/chat/<session_id>/reply", methods=["POST"])
@csrf.exempt
def chat_reply(session_id: str):
    """Send a reply from the admin to the user."""
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({"ok": False, "error": "Message cannot be empty"}), 400

    session = chat_repo.get_session(session_id)
    if not session:
        return jsonify({"ok": False, "error": "Session not found"}), 404

    try:
        # Add the message as 'human_agent'
        msg = chat_repo.add_message(
            session_id,
            sender_type="human_agent",
            text=text,
            sender_name=current_user.full_name,
        )

        # Ensure status is 'human' just in case
        if session["status"] != chat_repo.SESSION_STATUS_HUMAN:
            chat_repo.update_session_status(session_id, chat_repo.SESSION_STATUS_HUMAN)

        return jsonify({"ok": True, "message": msg})
    except Exception as exc:
        log.error("Admin chat reply failed: %s", exc)
        return jsonify({"ok": False, "error": "Failed to send reply"}), 500


@admin_bp.route("/chat/<session_id>/close", methods=["POST"])
@csrf.exempt
def chat_close(session_id: str):
    """Close the chat session."""
    try:
        chat_repo.update_session_status(session_id, chat_repo.SESSION_STATUS_CLOSED)
        chat_repo.add_message(session_id, "system", "Chat closed by admin.")
        return jsonify({"ok": True})
    except Exception as exc:
        log.error("Failed to close chat: %s", exc)
        return jsonify({"ok": False, "error": "Failed to close"}), 500