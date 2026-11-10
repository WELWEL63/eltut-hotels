"""
services/chatbot_service.py
───────────────────────────
The logic engine for the automated chatbot.

Public API
──────────
    process_user_message(session_id, text) -> dict
        Main entry point. Takes text, decides if bot can answer,
        or if it needs to hand over to a human.

    trigger_human_handover(session_id) -> dict
        Explicitly called when user clicks "Talk to a Human".

Design Notes:
    - No Flask request imports.
    - Uses regex/keyword matching for the "Simple Path" logic.
    - Reads from database via mongo/chat.py.
    - No external API costs.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from mongo import chat as chat_repo
from models import Package, Hotel, Destination
from extensions import db
from sqlalchemy import select

log = logging.getLogger(__name__)

# ── Bot Replies ─────────────────────────────────────────────────────
GREETING_MSG = (
    "Hello! I'm the ElTut assistant. "
    "I can help with booking questions, package details, or general travel info. "
    "How can I help you today?"
)

HUMAN_HANDOVER_MSG = (
    "I've let our team know you'd like to speak to a human. "
    "An agent will join this chat as soon as possible."
)

HUMAN_ACTIVE_MSG = (
    "You are currently connected to a human agent. Please wait for their reply."
)

FALLBACK_MSG = (
    "I'm not quite sure I understand that. "
    "You can ask me about our packages, hotels, or how to book. "
    "Or click 'Talk to a Human' below and a real person will help you!"
)

# ── Helper: Keyword matching ────────────────────────────────────────
def _match_and_reply(text: str) -> str | None:
    """
    Simple rule-based matching. Returns a reply string if matched,
    or None if the bot doesn't know the answer.
    """
    t = text.lower().strip()

    # 1. Greetings
    if re.search(r'\b(hello|hi|hey|greetings)\b', t):
        return "Hello! How can I help you with your Egypt trip today?"

    # 2. Payment / Booking queries
    if re.search(r'\b(pay|payment|paypal|card|checkout)\b', t):
        return (
            "You can pay securely via PayPal at checkout. "
            "If you don't have PayPal, you can still book and we will send "
            "a secure payment link via email!"
        )
    
    # 3. Cancellation queries
    if re.search(r'\b(cancel|cancellation|refund|policy)\b', t):
        return (
            "Our cancellation policies vary by package. "
            "Generally, you can cancel up to 7 days before departure for a refund. "
            "You can view the exact policy on the package detail page."
        )

    # 4. Flights/Transfer queries
    if re.search(r'\b(flight|airport|transfer|pickup)\b', t):
        return (
            "Most of our packages include flights and airport transfers. "
            "Look for the 'Flights Included' badge on the package card. "
            "If you don't see it, the package is land-only and we can arrange flights for you!"
        )

       # 5. Package questions (Dynamic)
    if "package" in t or "holiday" in t:
        try:
            for dest in db.session.scalars(select(Destination)):
                if dest.name.lower() in t:
                    return f"We have several amazing packages for {dest.name}! You can browse them all by clicking here: /packages?destination={dest.slug}"
        except Exception:
            pass
                
        return (
            "We have packages all across Egypt — from Nile cruises to Red Sea holidays! "
            "You can browse all our packages here: /packages"
        )
    
    # 6. Visa queries
    if re.search(r'\b(visa|passport|entry)\b', t):
        return (
            "Most visitors need a visa to enter Egypt. You can get an e-visa online "
            "or a visa-on-arrival at the airport. We recommend applying online before you travel."
        )

    # Fallback
    return None


# ── Public API ──────────────────────────────────────────────────────
def process_user_message(session_id: str, text: str) -> dict[str, Any]:
    """Main entry point for incoming messages."""
    session = chat_repo.get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found.")

    # 1. Save the user's message to DB
    chat_repo.add_message(session_id, "user", text)

    # 2. Check if a human is handling this session
    if session["status"] == chat_repo.SESSION_STATUS_HUMAN:
        # We don't auto-reply, but we return a flag so the frontend knows
        # it's waiting for the admin to type a response.
        return {"handled_by": "human", "status": "waiting_for_agent_reply"}

    # 3. If waiting for human, just acknowledge
    if session["status"] == chat_repo.SESSION_STATUS_WAITING:
        # The bot shouldn't reply while waiting, just save the msg.
        return {"handled_by": "system", "status": "waiting_for_agent"}

    # 4. Bot tries to answer
    bot_reply_text = _match_and_reply(text)
    
    if bot_reply_text:
        # Save the bot's reply
        chat_repo.add_message(session_id, "bot", bot_reply_text)
        return {
            "handled_by": "bot",
            "reply": bot_reply_text,
            "status": "bot"
        }
    else:
        # Bot doesn't know the answer. 
        # We can either return a fallback, OR auto-escalate.
        # Let's return the fallback, and let the user decide to click "Human".
        chat_repo.add_message(session_id, "bot", FALLBACK_MSG)
        return {
            "handled_by": "bot",
            "reply": FALLBACK_MSG,
            "status": "bot",
            "can_escalate": True
        }


def trigger_human_handover(session_id: str) -> dict[str, Any]:
    """Called when the user clicks 'Talk to a Human'."""
    session = chat_repo.get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found.")

    # If already with a human, do nothing
    if session["status"] == chat_repo.SESSION_STATUS_HUMAN:
        return {"status": "already_with_human"}

    # Change status to waiting
    chat_repo.update_session_status(session_id, chat_repo.SESSION_STATUS_WAITING)
    
    # Add a system message so the admin knows when the user requested help
    chat_repo.add_message(
        session_id, 
        "bot", 
        "User requested a human agent.",
        sender_name="System"
    )
    
    # Send the confirmation to the user
    chat_repo.add_message(session_id, "bot", HUMAN_HANDOVER_MSG)

    return {
        "status": chat_repo.SESSION_STATUS_WAITING,
        "reply": HUMAN_HANDOVER_MSG
    }


__all__ = [
    "process_user_message",
    "trigger_human_handover",
]