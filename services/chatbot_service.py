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
    - Rich knowledge base covering Egypt travel advice, UK specifics,
      culture, safety, weather, money, and site navigation.
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
    "Hello! 👋 I'm the ElTut Assistant. I can help you explore our packages, "
    "answer questions about Egypt, or connect you with our team. "
    "What are you looking to do today?"
)

HUMAN_HANDOVER_MSG = (
    "I've let our team know you'd like to speak to a human. "
    "An agent will join this chat as soon as possible."
)

HUMAN_ACTIVE_MSG = (
    "You are currently connected to a human agent. Please wait for their reply."
)

FALLBACK_MSG = (
    "I'm not quite sure I understand that. 🤔\n\n"
    "Here are some things I can help with:\n"
    "• **Explore:** Ask me about our Hotels, Packages, or Activities.\n"
    "• **Travel Advice:** Ask about Visas, Weather, Safety, or Money.\n"
    "• **Support:** Ask for our contact details (email/phone).\n\n"
    "Or click 'Talk to a Human' below and a real person will help you!"
)

# ── Helper: Keyword matching ────────────────────────────────────────
def _match_and_reply(text: str) -> str | None:
    """
    Advanced rule-based matching. Returns a reply string if matched,
    or None if the bot doesn't know the answer.
    """
    t = text.lower().strip()

    # ═══════════════════════════════════════════════════════════════
    # 1. CONTACT DETAILS & HUMAN SUPPORT
    # ═══════════════════════════════════════════════════════════════
    if re.search(r'\b(contact|email|phone|number|call|speak|support|help|agent|human|team)\b', t):
        return (
            "**We're here to help!** 🌍\n\n"
            "• **Email:** hello@eltuttours.com\n"
            "• **Phone:** 0800 124 376 (UK Freephone)\n"
            "• **WhatsApp:** +20 100 123 4567\n\n"
            "**Office Hours:** Monday – Saturday, 9:00 AM – 6:00 PM (GMT).\n\n"
            "If you need an immediate answer, you can also click **'Talk to a Human'** below and one of our agents will jump into this chat!"
        )

    # ═══════════════════════════════════════════════════════════════
    # 2. SITE NAVIGATION & CROSS-SELLING
    # ═══════════════════════════════════════════════════════════════
    if re.search(r'\b(website|site|browse|look|find|see|show me|options|what do you have)\b', t):
        return (
            "You can explore everything we offer right here on the website:\n\n"
            "• **Tour Packages:** [View Packages](/packages) — All-inclusive holidays.\n"
            "• **Hotels:** [View Hotels](/hotels) — From 3-star to luxury 5-star resorts.\n"
            "• **Activities:** [View Activities](/activities) — Diving, tours, and excursions.\n"
            "• **Custom Quote:** [Get a Quote](/quote/request) — Let us build your dream trip.\n\n"
            "Where would you like to start?"
        )

    if "package" in t or "holiday" in t or "tour" in t:
        try:
            for dest in db.session.scalars(select(Destination)):
                if dest.name.lower() in t:
                    return f"We have several amazing packages for **{dest.name}**! 🌴\n\nYou can browse them all here: [View {dest.name} Packages](/packages?destination={dest.slug})"
        except Exception:
            pass
        return "We have packages all across Egypt — from Nile cruises to Red Sea holidays! 🏖️\n\nYou can browse all our packages here: [View Tour Packages](/packages)"

    if "hotel" in t or "stay" in t or "room" in t or "accommodation" in t:
        return "We offer a wide range of hotels from 3-star to 5-star luxury resorts. 🏨\n\nYou can view all our hotels here: [View Hotels](/hotels)"

    if "activity" in t or "excursion" in t or "trip" in t or "things to do" in t:
        return "We have incredible activities — from scuba diving in the Red Sea to guided tours of the Pyramids! 🤿🏛️\n\nYou can see all activities here: [View Activities](/activities)"

    # ═══════════════════════════════════════════════════════════════
    # 3. GREETINGS & SMALL TALK
    # ═══════════════════════════════════════════════════════════════
    if re.search(r'\b(hello|hi|hey|greetings|good morning|good evening)\b', t):
        return "Hello! 👋 How can I help you with your Egypt trip today? I can answer questions about our packages, visas, safety, weather, or connect you with our team."
    
    if re.search(r'\b(thanks|thank you|cheers|great|awesome|perfect)\b', t):
        return "You're very welcome! 😊 Is there anything else I can help you with before you book?"
    
    if re.search(r'\b(bye|goodbye|see ya|talk later)\b', t):
        return "Goodbye! 👋 If you need anything else, just open this chat. Have a wonderful trip to Egypt!"

    # ═══════════════════════════════════════════════════════════════
    # 4. VISA, PASSPORT & ENTRY
    # ═══════════════════════════════════════════════════════════════
    if re.search(r'\b(visa|passport|entry|entry requirements|e-visa)\b', t):
        return (
            "🛂 **Visa & Entry Requirements**\n\n"
            "Most visitors need a visa to enter Egypt. The easiest options:\n"
            "• **E-visa (recommended):** Apply online at visa2egypt.gov.eg at least 7 days before travel. "
            "Single-entry from $30 USD; multiple-entry from $65 USD. Valid for stays up to 3 months.\n"
            "• **Visa on arrival:** Available at approved kiosks in the arrival hall. Around $25–36 USD, payable in cash. Valid for 30 days.\n"
            "• **Free Sinai stamp:** If you fly directly to Sharm El-Sheikh, Dahab, Nuweiba or Taba and stay only in South Sinai for up to 15 days, you get a free entry stamp. You cannot leave the Sinai region on this stamp.\n\n"
            "**Passport rule:** Must be valid for at least 6 months from your arrival date."
        )

    # ═══════════════════════════════════════════════════════════════
    # 5. WEATHER & BEST TIME TO VISIT
    # ═══════════════════════════════════════════════════════════════
    if re.search(r'\b(weather|temperature|hot|cold|climate|season|when to visit|best time|summer|winter)\b', t):
        return (
            "☀️ **Weather & Best Time to Visit**\n\n"
            "• **Best for sightseeing:** October – April. Mild, sunny days (20–28°C), perfect for the Pyramids and Luxor temples. December–January are coolest but busiest.\n"
            "• **Best for Red Sea beaches:** May – September. Warm sea, crystal-clear water, ideal for Hurghada and Sharm El-Sheikh diving. Inland cities get very hot (40°C+).\n"
            "• **Shoulder months (fewer crowds):** March–April and October–November. Pleasant weather and lower prices.\n\n"
            "**Heads up:** Late March and early April can bring *khamsin* sandstorms — reduced visibility for a day or two."
        )

    # ═══════════════════════════════════════════════════════════════
    # 6. MONEY, CARDS & TIPPING
    # ═══════════════════════════════════════════════════════════════
    if re.search(r'\b(money|currency|card|atm|tipping|tips|cash|exchange rate|egyptian pound|egp|bank)\b', t):
        return (
            "💵 **Money, Cards & Tipping**\n\n"
            "• **Currency:** Egyptian Pound (EGP). US dollars and major cards are widely accepted at hotels and large shops, but souks, taxis, and tips need EGP.\n"
            "• **ATMs:** Widely available in cities; withdraw EGP. Cards accepted at major monuments (Giza, Egyptian Museum, Luxor sites).\n"
            "• **Tipping (*baksheesh*):** Expected and part of daily life. Carry small bills — 10% of the bill for restaurants, small amounts for hotel staff, restroom attendants, and guides. Cash only.\n"
            "• **Bargaining:** Normal at souks and tourist markets. Start around half the asking price. Fixed prices apply in modern shops and restaurants."
        )

    # ═══════════════════════════════════════════════════════════════
    # 7. SAFETY & HEALTH
    # ═══════════════════════════════════════════════════════════════
    if re.search(r'\b(safe|safety|danger|scam|water|drink|vaccine|vaccination|health|doctor|hospital|emergency|police)\b', t):
        return (
            "🩺 **Safety & Health**\n\n"
            "• **Tap water:** Do NOT drink it. Stick to sealed bottled water, even for brushing teeth.\n"
            "• **Vaccines (UK travellers):** Hepatitis A and Typhoid are recommended. Hepatitis B for some. Rabies for longer stays. Malaria tablets are not needed for standard tourist routes. Book a travel health appointment 6–8 weeks before departure.\n"
            "• **Scams to avoid:** Ignore unsolicited 'gifts' or 'free' camel rides around the Pyramids. Agree prices in advance for horse carriages, boats and taxis. Only use licensed guides and reputable dive operators.\n"
            "• **Emergency numbers:** Police 122 · Tourist Police 126 · Ambulance 123.\n"
            "• **Travel insurance:** Essential. Consider medical evacuation cover — treatment for serious incidents may not be available locally."
        )

    # ═══════════════════════════════════════════════════════════════
    # 8. TRANSPORT & GETTING AROUND
    # ═══════════════════════════════════════════════════════════════
    if re.search(r'\b(transport|taxi|uber|careem|metro|train|bus|getting around|car hire|driving)\b', t):
        return (
            "🚕 **Transport & Getting Around**\n\n"
            "• **Ride-hailing apps (best option):** Uber, Careem, inDrive and Bolt are widely used, cheaper than street taxis, and lock in the price before you ride. Use them in Cairo and Alexandria.\n"
            "• **Street taxis:** Insist the meter is on. For women travelling alone, sit in the back seat.\n"
            "• **Cairo Metro:** Cheap, efficient, English signage. Runs ~5:15 AM to 12:30 AM. Women-only cars at the front of each train.\n"
            "• **Tuk-tuks:** Great for short trips in Cairo's narrow streets. Agree the price before you get in.\n"
            "• **Between cities:** Flights are the safest option for long distances. Trains run but infrastructure is older. Avoid driving yourself — road rules are rarely followed."
        )

    # ═══════════════════════════════════════════════════════════════
    # 9. CULTURE, ETIQUETTE & RELIGION
    # ═══════════════════════════════════════════════════════════════
    if re.search(r'\b(culture|etiquette|customs|mosque|ramadan|dress|clothing|modest|photography|temple|religion)\b', t):
        return (
            "🕌 **Culture & Etiquette**\n\n"
            "• **Cultural dress code:** Egypt is conservative — cover shoulders and knees, especially at religious sites. Loose, breathable cotton or linen keeps you cool and respectful. Women should bring a scarf to cover their head at mosques.\n"
            "• **Greetings:** A handshake is normal between men. Wait for a woman to offer her hand first. Say *'As-salaam alaikum'* (peace be upon you) — the reply is *'Wa alaikum as-salaam'*.\n"
            "• **Photography:** Ask permission before photographing people. Some sites prohibit photography inside tombs (Valley of the Kings). Never photograph military or police buildings.\n"
            "• **Ramadan:** During the holy month, avoid eating, drinking or smoking in public during daylight. Many restaurants close; some open for tourists in hotels.\n"
            "• **Public affection:** Keep it modest — Egypt is a conservative society."
        )

    # ═══════════════════════════════════════════════════════════════
    # 10. PACKING & WHAT TO BRING
    # ═══════════════════════════════════════════════════════════════
    if re.search(r'\b(pack|packing|bring|wear|clothes|sunscreen|adaptor|plug|sim card|esim)\b', t):
        return (
            "🎒 **Packing & What to Bring**\n\n"
            "• **Essentials:** Sun hat, sunglasses, high-SPF sunscreen, refillable water bottle, portable charger, comfortable walking shoes, and wet wipes (many public bathrooms have no toilet paper).\n"
            "• **Seasonal layers:** Desert evenings can be cold (down to ~7°C in winter). Pack a jumper or light jacket even in spring/autumn.\n"
            "• **Plugs:** Egypt uses Type C and Type F plugs (same as Europe). UK travellers will need a standard European adaptor.\n"
            "• **SIM Cards:** You can buy a local Vodafone or Orange SIM at the airport with your passport. eSIMs (like Airalo) also work well."
        )

    # ═══════════════════════════════════════════════════════════════
    # 11. FOOD & DRINK
    # ═══════════════════════════════════════════════════════════════
    if re.search(r'\b(food|eat|restaurant|vegan|vegetarian|halal|alcohol|beer|wine|street food)\b', t):
        return (
            "🍽️ **Food & Drink**\n\n"
            "• **Food safety:** Avoid raw salads and unpeeled fruit from street vendors. Stick to hot, freshly cooked food.\n"
            "• **Vegetarian/Vegan:** Very accommodating! Dishes like Koshari (lentils, rice, pasta), Falafel (Ta'ameya), and Mahshi (stuffed vegetables) are naturally vegan. Just ask for *'bidoon lahm'* (no meat).\n"
            "• **Halal:** Almost all food in Egypt is Halal.\n"
            "• **Alcohol:** Available in hotels, bars, and licensed restaurants, but not widely sold in local shops. Drinking in public is frowned upon."
        )

    # ═══════════════════════════════════════════════════════════════
    # 12. UK SPECIFIC & EXPAT LIVING
    # ═══════════════════════════════════════════════════════════════
    if re.search(r'\b(uk|british|uk citizen|living in egypt|expat|move to egypt|residency)\b', t):
        return (
            "🇬🇧 **UK Travellers & Expat Living**\n\n"
            "• **UK Travellers:** The FCDO advises against all but essential travel to the Governorate of North Sinai, but the rest of Egypt (Cairo, Red Sea, Luxor, Aswan) is safe and welcoming. Ensure your passport is valid for 6 months. UK plugs will need a Type C/F adaptor.\n"
            "• **Living in Egypt (Expats):** Many Brits live in Hurghada, Sharm, and Cairo. You can get a residency visa through property investment or retirement. Healthcare is cheap but private hospitals are recommended. The cost of living is significantly lower than the UK."
        )

    # ═══════════════════════════════════════════════════════════════
    # 13. PAYMENT, BOOKING & CANCELLATION (Site Specific)
    # ═══════════════════════════════════════════════════════════════
    if re.search(r'\b(pay|payment|paypal|card|checkout|deposit|secure)\b', t):
        return (
            "💳 **Payment & Checkout**\n\n"
            "You can pay securely via PayPal at checkout. "
            "If you don't have PayPal, you can still book and we will send "
            "a secure payment link via email! For packages, a deposit is usually required, with the balance due before travel."
        )

    if re.search(r'\b(cancel|cancellation|refund|policy)\b', t):
        return (
            "📝 **Cancellation Policy**\n\n"
            "Our cancellation policies vary by package and hotel. "
            "Generally, you can cancel up to 7 days before departure for a full refund. "
            "You can view the exact policy on the specific package detail page before booking."
        )

    if re.search(r'\b(flight|airport|transfer|pickup|baggage|luggage)\b', t):
        return (
            "✈️ **Flights & Transfers**\n\n"
            "Most of our packages include flights and airport transfers. "
            "Look for the 'Flights Included' badge on the package card. "
            "If you don't see it, the package is land-only and we can arrange flights for you! "
            "Luggage allowances depend on the airline (usually 20-23kg checked)."
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
        return {"handled_by": "human", "status": "waiting_for_agent_reply"}

    # 3. If waiting for human, just acknowledge
    if session["status"] == chat_repo.SESSION_STATUS_WAITING:
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