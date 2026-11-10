"""
mongo/chat.py
─────────────
Repository for the Chatbot.
Includes an in-memory fallback that persists to a local JSON file
so the Admin panel and the User frontend can share data even without MongoDB.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from bson import ObjectId
from mongo.client import _col

log = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────
SESSION_STATUS_BOT: str = "bot"
SESSION_STATUS_WAITING: str = "waiting_for_human"
SESSION_STATUS_HUMAN: str = "human"
SESSION_STATUS_CLOSED: str = "closed"
VALID_SESSION_STATUSES = (SESSION_STATUS_BOT, SESSION_STATUS_WAITING, SESSION_STATUS_HUMAN, SESSION_STATUS_CLOSED)

# Note: "system" is now a valid sender type for "Agent joined" / "Chat closed" notices
VALID_SENDER_TYPES = ("user", "bot", "human_agent", "system")

# ── LOCAL JSON DB (Fallback for local testing) ──────────────────────
DB_FILE = "chat_db.json"

def _load_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"sessions": {}, "messages": {}}
    return {"sessions": {}, "messages": {}}

def _save_db(db: dict) -> None:
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, default=str)
    except Exception as e:
        log.error(f"Failed to save chat DB: {e}")

def _get_col(collection_name: str):
    try:
        return _col(collection_name)
    except Exception:
        return None

def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()

# ── Sessions ────────────────────────────────────────────────────────
def create_session(user_id: int | None = None, guest_name: str | None = None) -> dict[str, Any]:
    session_id = str(ObjectId())
    doc = {
        "id": session_id,
        "user_id": user_id,
        "guest_name": guest_name or "Guest",
        "status": SESSION_STATUS_BOT,
        "created_at": _now_utc(),
        "updated_at": _now_utc(),
        "last_message_preview": "Started a new chat",
    }
    
    col = _get_col("chat_sessions")
    if col is None:
        db = _load_db()
        db["sessions"][session_id] = doc
        _save_db(db)
    else:
        col.insert_one({**doc, "_id": ObjectId(session_id)})
    return doc

def get_session(session_id: str) -> dict[str, Any] | None:
    col = _get_col("chat_sessions")
    if col is None:
        db = _load_db()
        return db["sessions"].get(session_id)
    
    try:
        doc = col.find_one({"_id": ObjectId(session_id)})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc
    except Exception:
        return None

def get_active_session(user_id: int | None = None) -> dict[str, Any] | None:
    col = _get_col("chat_sessions")
    if col is None:
        db = _load_db()
        for s in db["sessions"].values():
            if s["status"] != SESSION_STATUS_CLOSED and s["user_id"] == user_id:
                return s
        return None
        
    try:
        query = {"status": {"$ne": SESSION_STATUS_CLOSED}}
        if user_id is not None:
            query["user_id"] = user_id
        doc = col.find_one(query, sort=[("created_at", -1)])
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc
    except Exception:
        return None

def update_session_status(session_id: str, status: str) -> bool:
    if status not in VALID_SESSION_STATUSES:
        raise ValueError(f"Invalid status: {status}")
        
    col = _get_col("chat_sessions")
    if col is None:
        db = _load_db()
        if session_id in db["sessions"]:
            db["sessions"][session_id]["status"] = status
            db["sessions"][session_id]["updated_at"] = _now_utc()
            _save_db(db)
        return True
        
    try:
        col.update_one({"_id": ObjectId(session_id)}, {"$set": {"status": status, "updated_at": _now_utc()}})
        return True
    except Exception:
        return False

# ── Messages ────────────────────────────────────────────────────────
def add_message(session_id: str, sender_type: str, text: str, sender_name: str | None = None) -> dict[str, Any]:
    if sender_type not in VALID_SENDER_TYPES:
        raise ValueError(f"Invalid sender_type: {sender_type}")

    msg_id = str(ObjectId())
    now = _now_utc()
    msg_doc = {
        "id": msg_id,
        "session_id": session_id,
        "sender_type": sender_type,
        "sender_name": sender_name,
        "text": text.strip(),
        "created_at": now,
    }
    
    col = _get_col("chat_messages")
    if col is None:
        db = _load_db()
        if session_id not in db["messages"]:
            db["messages"][session_id] = []
        db["messages"][session_id].append(msg_doc)
        
        if session_id in db["sessions"]:
            db["sessions"][session_id]["updated_at"] = now
            db["sessions"][session_id]["last_message_preview"] = text[:50]
        _save_db(db)
    else:
        try:
            col.insert_one({**msg_doc, "_id": ObjectId(msg_id), "session_id": ObjectId(session_id)})
            _get_col("chat_sessions").update_one(
                {"_id": ObjectId(session_id)},
                {"$set": {"updated_at": now, "last_message_preview": text[:50]}}
            )
        except Exception:
            pass

    return msg_doc

def get_messages(session_id: str, limit: int = 100) -> list[dict[str, Any]]:
    col = _get_col("chat_messages")
    if col is None:
        db = _load_db()
        return db["messages"].get(session_id, [])
        
    try:
        cursor = col.find({"session_id": ObjectId(session_id)}).sort("created_at", 1).limit(limit)
        return [ {"id": str(doc.pop("_id")), **doc} for doc in cursor ]
    except Exception:
        return []

# ── Admin Queries ───────────────────────────────────────────────────
def list_sessions_waiting_for_human(limit: int = 20) -> list[dict[str, Any]]:
    col = _get_col("chat_sessions")
    if col is None:
        db = _load_db()
        return [s for s in db["sessions"].values() if s["status"] == SESSION_STATUS_WAITING][:limit]
        
    try:
        cursor = col.find({"status": SESSION_STATUS_WAITING}).sort("updated_at", 1).limit(limit)
        return [ {"id": str(doc.pop("_id")), **doc} for doc in cursor ]
    except Exception:
        return []

def list_active_human_sessions(limit: int = 20) -> list[dict[str, Any]]:
    col = _get_col("chat_sessions")
    if col is None:
        db = _load_db()
        return [s for s in db["sessions"].values() if s["status"] == SESSION_STATUS_HUMAN][:limit]
        
    try:
        cursor = col.find({"status": SESSION_STATUS_HUMAN}).sort("updated_at", -1).limit(limit)
        return [ {"id": str(doc.pop("_id")), **doc} for doc in cursor ]
    except Exception:
        return []