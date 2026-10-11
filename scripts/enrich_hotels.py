"""
scripts/enrich_hotels.py
────────────────────────
Rich enrichment for all 180 hotels — descriptions, facilities, FAQs,
tips, policies, coordinates, and map links.

TWO TIERS:

  CURATED — hand-written, brand-specific content for ~40 recognizable
    hotels (Hilton, Mövenpick, Sheraton, Sonesta, Marriott, Fairmont,
    Kempinski, Radisson, Ritz-Carlton, Jaz, Iberotel, Titanic, Pyramisa,
    Steigenberger, Savoy, Sunrise, Rixos). Each has a 150-200 word
    description, brand-accurate facilities, and destination-specific FAQs.

  TEMPLATE — destination + star-aware content for the remainder, marked
    with [Sample content — verify before publishing].

USAGE
    python scripts/enrich_hotels.py --dry-run
    python scripts/enrich_hotels.py
    python scripts/enrich_hotels.py --only-curated
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import (  # noqa: E402
    Destination,
    Hotel,
    HotelFacility,
    HotelInclusion,
    HotelExclusion,
    HotelFAQ,
    HotelTip,
)


# ══════════════════════════════════════════════════════════════════
#  Destination centres (for map embeds)
# ══════════════════════════════════════════════════════════════════
DEST_COORDS: dict[str, tuple[float, float]] = {
    "hurghada":      (27.2579, 33.8116),
    "sharm":         (27.9158, 34.3299),
    "luxor":         (25.6872, 32.6396),
    "aswan":         (24.0889, 32.8998),
    "cairo":         (30.0444, 31.2357),
    "dahab":         (28.5094, 34.5135),
    "taba":          (29.4928, 34.8962),
    "nile":          (25.6872, 32.6396),
    "marsa":         (25.0667, 34.9000),
    "el gouna":      (27.3950, 33.6780),
    "soma bay":      (26.8470, 33.9880),
    "makadi":        (26.9940, 33.9080),
    "nuweiba":       (29.0333, 34.6667),
    "tiran":         (27.9500, 34.4000),
    "naama":         (27.9120, 34.3300),
    "sahl hasheesh": (27.0460, 33.8800),
    "marsa alam":    (25.0667, 34.9000),
}


# ══════════════════════════════════════════════════════════════════
#  Facility type mapping — DB constraint only allows:
#     general, wellness, dining, sport, family, business, other
# ══════════════════════════════════════════════════════════════════
_ALLOWED_FACILITY_TYPES = {
    "general", "wellness", "dining", "sport", "family", "business", "other",
}
_FACILITY_TYPE_MAP = {
    "pool":         "general",
    "spa":          "wellness",
    "hammam":       "wellness",
    "beach":        "general",
    "wifi":         "general",
    "connectivity": "general",
    "service":      "general",
    "transport":    "general",
    "bar":          "dining",
    "restaurant":   "dining",
    "gym":          "sport",
    "fitness":      "sport",
    "kids":         "family",
    "shopping":     "other",
    "entertainment": "other",
    "golf":         "sport",
    "dive":         "sport",
}


def _safe_facility_type(raw: str | None) -> str:
    """Map any facility type string to one the DB will accept."""
    t = (raw or "").strip().lower()
    if t in _ALLOWED_FACILITY_TYPES:
        return t
    return _FACILITY_TYPE_MAP.get(t, "other")


# ══════════════════════════════════════════════════════════════════
#  CURATED HOTELS — hand-written, brand-specific content
# ══════════════════════════════════════════════════════════════════
CURATED: dict[str, dict] = {

    # ═══════════════════════════════════════════════════════════════
    #  HILTON (8 properties)
    # ═══════════════════════════════════════════════════════════════
    "hilton luxor": {
        "description": (
            "Set on the east bank of the Nile amid five acres of lush gardens, "
            "Hilton Luxor Resort & Spa is a serene five-star retreat a short drive "
            "from the greatest open-air museum on earth. Rooms and suites open onto "
            "private balconies with garden or river views, and the property's "
            "riverfront infinity pool — with the West Bank's Theban hills as a "
            "backdrop — is one of the most photographed in Upper Egypt. The hotel's "
            "signature spa draws on ancient Egyptian rituals, and its three "
            "restaurants span Mediterranean, Oriental, and international cuisine. "
            "A complimentary river shuttle runs across to the West Bank, putting "
            "the Valley of the Kings and Hatshepsut's Temple within easy reach. "
            "Evenings on the terrace, with feluccas drifting past and the "
            "illuminated Luxor Temple glowing in the distance, are unforgettable."
        ),
        "neighborhood": (
            "Positioned on the Nile corniche in Luxor's quiet northern district, "
            "the hotel is 15 minutes' drive from Luxor Temple and the Luxor Museum, "
            "and about 20 minutes from the ferry to the Valley of the Kings. The "
            "winter palace gardens, Luxor souk, and the Luxor Museum of Mummification "
            "are all within a short taxi ride. Luxor International Airport is 20 "
            "minutes away."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00. Valid passport or ID required.\n"
            "Children welcome; babysitting available on request.\n"
            "No smoking inside guest rooms or indoor restaurants.\n"
            "Quiet hours observed 23:00 – 07:00.\n"
            "Pets are not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 72 hours before check-in for flexible rates; "
            "cancellations within 72 hours are charged the first night. Non-refundable "
            "rates apply in full at time of booking. No-shows are charged the full "
            "stay. Refunds are processed within 5-7 business days."
        ),
        "check_in_details": (
            "Valid passport required at check-in. A credit card pre-authorisation of "
            "the room rate plus incidentals is taken on arrival and released at "
            "check-out. Airport transfers can be arranged 24 hours in advance. "
            "Early check-in and late check-out subject to availability."
        ),
        "tips": (
            "Book a Nile-view room — the sunset over the Theban hills is unforgettable.\n"
            "Bring light layers for early-morning Valley of the Kings excursions.\n"
            "The spa's Egyptian-cotton massage is best booked a day in advance.\n"
            "Try the rooftop restaurant at sunset — the illumination of Luxor Temple is spectacular.\n"
            "Ask the concierge about private Egyptologist guides — worth every penny."
        ),
        "facilities": [
            ("Riverside infinity swimming pool", "pool", 1),
            ("Second outdoor pool with sun terrace", "pool", 1),
            ("Full-service spa & traditional hammam", "spa", 1),
            ("Three restaurants: Mediterranean, Oriental, international", "dining", 3),
            ("Lobby bar & poolside cocktail bar", "dining", 2),
            ("24-hour fitness centre", "sport", 1),
            ("Complimentary river shuttle to West Bank", "transport", 1),
            ("Free high-speed Wi-Fi throughout", "connectivity", 1),
            ("24-hour concierge & tour desk", "service", 1),
            ("Meeting & event facilities", "business", 3),
        ],
    },

    "hilton waterfalls": {
        "description": (
            "Built around cascading pools and tropical gardens in the Hadaba area "
            "of Sharm El Sheikh, Hilton Waterfalls offers a relaxed, family-friendly "
            "resort experience minutes from Naama Bay. Four pool terraces, a private "
            "beach, and easy access to the reefs of Ras Mohammed National Park make "
            "it a solid choice for couples, families, and divers alike. Rooms are "
            "spacious and contemporary, with garden or pool views; several restaurants "
            "cover Italian, Middle Eastern, and international cuisine, and the resort "
            "runs a full animation programme for children and adults. The Sharm El "
            "Sheikh airport is only 20 minutes away, making it a convenient base for "
            "a Red Sea escape."
        ),
        "neighborhood": (
            "In the Hadaba district of Sharm El Sheikh, roughly 10 minutes from "
            "Naama Bay promenade and its restaurants, cafés, and nightlife. The Old "
            "Market and Il Mercato shopping mall are within easy reach by taxi. "
            "Sharm El Sheikh International Airport is 25 minutes by car, and the "
            "Ras Mohammed National Park is a 40-minute drive south."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "Children's pool and Kids' Club available free of charge.\n"
            "No smoking inside guest rooms.\n"
            "Pool hours 07:00 – 20:00. Lifeguards on duty.\n"
            "Pets are not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in for flexible bookings. "
            "Cancellations within 48 hours are charged one night. Non-refundable rates "
            "are charged in full at booking. Peak season (Christmas, New Year, Easter) "
            "may have stricter policies — see rate conditions."
        ),
        "check_in_details": (
            "Valid passport required. A pre-authorisation of the first night plus "
            "incidentals is taken on arrival. All-inclusive wristbands are issued at "
            "check-in. Airport transfers can be arranged through the concierge."
        ),
        "tips": (
            "The upper-pool terraces are quieter in the morning — great for early swims.\n"
            "Bring reef-safe sunscreen — it protects the Red Sea coral.\n"
            "Book snorkelling or diving trips to Ras Mohammed through the concierge.\n"
            "The animation team's evening shows are surprisingly good — worth catching.\n"
            "Ask for a room away from the pool bar if you prefer early nights."
        ),
        "facilities": [
            ("Four cascading outdoor pools", "pool", 4),
            ("Private beach with sun loungers", "beach", 1),
            ("Kids' club, playground & children's pool", "family", 3),
            ("Two restaurants + lobby bar", "dining", 3),
            ("Full-service spa & wellness centre", "spa", 1),
            ("Fitness centre", "sport", 1),
            ("Free Wi-Fi in public areas & rooms", "connectivity", 1),
            ("24-hour reception & concierge", "service", 1),
        ],
    },

    "hilton hurghada plaza": {
        "description": (
            "Directly on the Red Sea seafront just minutes from Hurghada's marina, "
            "Hilton Hurghada Plaza pairs bright, contemporary rooms with a private "
            "beach and easy access to some of the best snorkelling and dive sites "
            "in the northern Red Sea. The hotel's pool area overlooks the water, "
            "and its restaurants and bars serve everything from Egyptian mezze to "
            "grilled seafood. Dive and water-sports operators are on-site, and the "
            "marina — with its yachts, cafés, and evening promenade — is a five-"
            "minute walk away."
        ),
        "neighborhood": (
            "On the Hurghada seafront promenade, walking distance to the marina, "
            "Sheraton Road shopping strip, and the cafés and restaurants of El Dahar. "
            "Hurghada International Airport is 15 minutes by car. The dive sites of "
            "Giftun Island and Orange Bay are 45 minutes by boat."
        ),
        "house_rules": (
            "Check-in from 15:00, check-out by 12:00.\n"
            "No smoking inside guest rooms — designated areas on terraces.\n"
            "Children under 12 must be supervised at the pool and beach.\n"
            "Quiet hours 23:00 – 07:00.\n"
            "Pets are not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged the first night. Non-refundable rates are charged "
            "in full. High season (Dec-Jan, Easter) may apply stricter terms."
        ),
        "check_in_details": (
            "Valid passport required. Credit card pre-authorisation of the stay plus "
            "incidentals is taken on arrival. Airport pick-up can be pre-arranged. "
            "Dive bookings should be made 24 hours in advance during high season."
        ),
        "tips": (
            "Ask for a sea-view room on a high floor — the Red Sea sunsets are spectacular.\n"
            "Snorkelling gear is available on-site at better rates than the marina.\n"
            "Try the Egyptian breakfast — ful medames and fresh flatbread.\n"
            "Book a Giftun Island boat trip early — the best departures sell out.\n"
            "The seafood grill is the best value restaurant in the hotel."
        ),
        "facilities": [
            ("Private beach with sun loungers & parasols", "beach", 1),
            ("Two outdoor swimming pools", "pool", 2),
            ("PADI dive centre & water-sports desk", "sport", 2),
            ("Two restaurants + beach bar", "dining", 3),
            ("Fitness centre", "sport", 1),
            ("Spa & massage services", "spa", 1),
            ("Free Wi-Fi throughout", "connectivity", 1),
            ("24-hour reception & concierge", "service", 1),
        ],
    },

    "hilton dahab": {
        "description": (
            "Low-rise, laid-back, and wrapped in palm gardens, Hilton Dahab Resort "
            "sits on a private stretch of beach in Dahab — the Sinai's bohemian "
            "diving town. The hotel's house reef, accessible straight from the "
            "beach, is ideal for beginner and intermediate snorkellers, while the "
            "legendary Blue Hole is a 20-minute drive up the coast. Guest rooms "
            "are simple and comfortable; the pool terrace is quiet and relaxing; "
            "and the hotel's dive centre runs PADI courses for all levels. Dahab's "
            "main promenade, with its cafés, craft stalls, and legendary evening "
            "atmosphere, is just five minutes away."
        ),
        "neighborhood": (
            "On the Dahab coast, five minutes' walk from Dahab's main promenade and "
            "its cafés, dive shops, and craft stalls. Sharm El Sheikh International "
            "Airport is about 90 minutes by road — but Dahab's slower pace is the "
            "whole point. The Blue Hole and the Sinai's best shore dives are within "
            "easy reach."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "Dive equipment can be stored on-site.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome; lifeguards on duty at the pool.\n"
            "Pets are not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged one night. Non-refundable rates charged in full. "
            "Dive packages cancelled within 24 hours are non-refundable."
        ),
        "check_in_details": (
            "Valid passport required. Pre-authorisation of the first night plus "
            "incidentals taken on arrival. Dive certification cards should be "
            "presented if booking dives. Airport transfers can be arranged — "
            "allow 90 minutes each way."
        ),
        "tips": (
            "The house reef is best snorkelled at high tide.\n"
            "Rent a bicycle to reach the Blue Hole — the coastal road is beautiful.\n"
            "Evenings in Dahab are cooler than Sharm — pack a light jumper.\n"
            "Book PADI courses a week ahead in high season.\n"
            "Dahab's evening promenade is worth walking every night — dinner is cheap and delicious."
        ),
        "facilities": [
            ("Private beach with house reef", "beach", 1),
            ("Outdoor swimming pool", "pool", 1),
            ("PADI dive centre with rental equipment", "sport", 1),
            ("Restaurant + beach bar", "dining", 2),
            ("Spa treatments & massage", "spa", 1),
            ("Wi-Fi in public areas", "connectivity", 1),
            ("24-hour reception", "service", 1),
        ],
    },

    "hilton sharm dreams": {
        "description": (
            "Set amid landscaped gardens in the heart of Sharm El Sheikh, Hilton "
            "Sharm Dreams offers a comfortable base for exploring the Sinai. The "
            "hotel's two pools, private beach, and multiple restaurants cover all "
            "the essentials, and its location near Naama Bay makes it easy to "
            "combine lazy resort days with the bay's nightlife and shopping. Guest "
            "rooms are bright and well-appointed, with balconies overlooking the "
            "gardens or pools."
        ),
        "neighborhood": (
            "In the centre of Sharm El Sheikh, walking distance to Naama Bay. "
            "Sharm El Sheikh International Airport is 15 minutes by car. Ras "
            "Mohammed National Park is 40 minutes south."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Pool and beach hours 07:00 – sunset.\n"
            "Children welcome; supervised at all times.\n"
            "Pets are not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged the first night. Non-refundable rates charged in full."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation for incidentals on arrival."
        ),
        "tips": (
            "Ask for a pool-view room with a balcony.\n"
            "Naama Bay is a 10-minute walk — go for the evening promenade.\n"
            "Book snorkelling trips early — the best operators fill up fast.\n"
            "The Italian restaurant is the best on-site."
        ),
        "facilities": [
            ("Two outdoor swimming pools", "pool", 2),
            ("Private beach access", "beach", 1),
            ("Multiple restaurants + bar", "dining", 3),
            ("Fitness centre", "sport", 1),
            ("Spa & massage services", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    "hilton sharm fayrouz": {
        "description": (
            "A relaxed resort in the Ras Um Sid area of Sharm El Sheikh, Hilton "
            "Sharm Fayrouz offers comfortable rooms, a private beach, and easy "
            "access to some of the best snorkelling on the Sinai coast. The "
            "hotel's gardens are lush and mature, its pool area is generous, and "
            "its restaurants cover Egyptian, Italian, and international cuisine. "
            "Ras Um Sid reef — a superb shore dive — is a short walk away."
        ),
        "neighborhood": (
            "In Ras Um Sid, 10 minutes from Naama Bay and 20 minutes from Sharm "
            "El Sheikh airport. The reef at Ras Um Sid is walking distance from "
            "the hotel."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Later cancellations "
            "charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival for incidentals."
        ),
        "tips": (
            "The nearby Ras Um Sid reef is superb for shore diving.\n"
            "Ask for a garden-view room — quieter and greener.\n"
            "The buffet breakfast is generous — arrive hungry.\n"
            "Book the hotel shuttle to Naama Bay for easy evenings out."
        ),
        "facilities": [
            ("Outdoor swimming pool", "pool", 1),
            ("Private beach access", "beach", 1),
            ("Restaurant + bar", "dining", 2),
            ("Fitness centre", "sport", 1),
            ("Spa treatments", "spa", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    "hilton sharks bay": {
        "description": (
            "Spread along a private stretch of coastline in Sharks Bay, Hilton "
            "Sharks Bay Resort is a peaceful retreat close to some of the most "
            "spectacular reefs in the northern Red Sea. The hotel's own house "
            "reef, accessible from the jetty, is excellent for snorkelling and "
            "beginners' dives. Guest rooms are set in low-rise buildings amid "
            "gardens, and the resort offers three pools, multiple restaurants, "
            "and a full dive centre."
        ),
        "neighborhood": (
            "In Sharks Bay, 10 minutes from Sharm El Sheikh airport and 15 "
            "minutes from Naama Bay. Some of the best shore dives in the region "
            "are directly accessible from the hotel jetty."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Snorkelling from the jetty is at guests' own risk.\n"
            "Children must be supervised at the jetty and reef.\n"
            "Pets are not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged the first night. Dive packages have separate terms."
        ),
        "check_in_details": (
            "Valid passport required. Pre-authorisation for incidentals on arrival. "
            "Dive certification required for reef dives from the jetty."
        ),
        "tips": (
            "The house reef is excellent — bring an underwater camera.\n"
            "Snorkel at high tide for the best visibility.\n"
            "Book a night dive — bioluminescence is unforgettable.\n"
            "Ask about the PADI open-water course — the hotel dive centre is well-regarded."
        ),
        "facilities": [
            ("Three outdoor swimming pools", "pool", 3),
            ("Private beach with house reef & jetty", "beach", 1),
            ("PADI dive centre", "sport", 1),
            ("Multiple restaurants + bars", "dining", 3),
            ("Full-service spa", "spa", 1),
            ("Fitness centre", "sport", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    "hilton long beach": {
        "description": (
            "A large, modern resort on one of Hurghada's longest private beaches, "
            "Hilton Long Beach Resort & Spa offers extensive pool areas, several "
            "restaurants, and a broad range of sports and entertainment. The "
            "hotel's reef is good for snorkelling, and the on-site dive centre "
            "runs courses and trips. Guest rooms are contemporary, and many have "
            "sea views."
        ),
        "neighborhood": (
            "On the Hurghada coast, 15 minutes from the airport and 10 minutes "
            "from the marina and Sheraton Road shopping district."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged the first night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival."
        ),
        "tips": (
            "Ask for a sea-view room on a high floor.\n"
            "The hotel reef is best snorkelled in the morning.\n"
            "Book a Giftun Island boat trip through the concierge.\n"
            "Try the beachside grill — best value on-site."
        ),
        "facilities": [
            ("Multiple outdoor pools", "pool", 3),
            ("Long private beach with reef", "beach", 1),
            ("Dive centre & water sports", "sport", 1),
            ("Multiple restaurants + bars", "dining", 4),
            ("Full-service spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    "hilton hurghada resort": {
        "description": (
            "Overlooking the Red Sea with its own private beach and extensive "
            "pools, Hilton Hurghada Resort combines classic five-star service "
            "with easy access to Hurghada's dive sites and marina. The hotel's "
            "restaurants cover international, Mediterranean, and Egyptian "
            "cuisine; the spa offers hammam and massage rituals; and the dive "
            "centre runs courses for all levels."
        ),
        "neighborhood": (
            "On the Hurghada seafront, 15 minutes from the airport and 10 minutes "
            "from the marina and Sheraton Road."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged the first night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival."
        ),
        "tips": (
            "Book a sea-view room for the best Red Sea sunsets.\n"
            "The dive centre is well-equipped — courses fill fast in high season.\n"
            "Try the Egyptian restaurant for authentic local dishes.\n"
            "Ask about the shuttle to the marina."
        ),
        "facilities": [
            ("Multiple outdoor pools", "pool", 3),
            ("Private beach with sun loungers", "beach", 1),
            ("Dive centre", "sport", 1),
            ("Multiple restaurants + bars", "dining", 4),
            ("Full-service spa", "spa", 1),
            ("Fitness centre", "sport", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    #  MÖVENPICK (2 properties)
    # ═══════════════════════════════════════════════════════════════
    "movenpick resort sharm": {
        "description": (
            "Carved into the cliffs above Naama Bay, Mövenpick Resort Sharm El "
            "Sheikh is a multi-level resort of whitewashed terraces, cascading "
            "pools, and panoramic Red Sea views. Swiss hospitality meets Egyptian "
            "warmth here: the hotel is famous for its daily chocolate hour, its "
            "excellent breakfast spread, and its funicular lift down to a private "
            "beach. Three restaurants span Mediterranean, Oriental, and seafood "
            "cuisine, while the spa and wellness centre offers treatments using "
            "Egyptian botanicals. Rooms are spread across the terraced levels, "
            "with balconies facing the sea, the gardens, or the pool."
        ),
        "neighborhood": (
            "Perched above Naama Bay, a 5-minute shuttle or 15-minute walk to the "
            "promenade, restaurants, and nightlife. Sharm El Sheikh International "
            "Airport is 20 minutes by car. Ras Mohammed National Park is 40 minutes "
            "south, and the famous Il Mercato shopping mall is 10 minutes away."
        ),
        "house_rules": (
            "Check-in from 15:00, check-out by 12:00.\n"
            "The funicular to the beach operates 07:00 – 22:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome; kids' club free for guests aged 4-12.\n"
            "Quiet hours 23:00 – 07:00."
        ),
        "cancellation": (
            "Free cancellation up to 72 hours before check-in for flexible rates. "
            "Cancellations within 72 hours are charged the first night. Non-refundable "
            "rates are charged in full at booking. Peak periods (Christmas, New Year, "
            "Easter) have stricter policies — check rate conditions."
        ),
        "check_in_details": (
            "Valid passport required. A credit card pre-authorisation of the first "
            "night plus incidentals is taken on arrival. Airport transfers can be "
            "arranged 24 hours in advance. Chocolates at check-in — a Mövenpick signature."
        ),
        "tips": (
            "The funicular down to the private beach is a highlight — ride it at sunset.\n"
            "Book a table at the cliff-top restaurant for dinner with a view.\n"
            "Daily chocolate hour (typically 4-5pm) — don't miss it.\n"
            "Ask about the daily shuttle to Naama Bay — it runs several times a day.\n"
            "Snorkel off the private beach — the reef is surprisingly rich."
        ),
        "facilities": [
            ("Cascading pools across multiple terraces", "pool", 4),
            ("Private beach with funicular access", "beach", 1),
            ("Three restaurants + bars", "dining", 4),
            ("Full-service spa & wellness centre", "spa", 1),
            ("Fitness centre", "sport", 1),
            ("Kids' club", "family", 1),
            ("Free high-speed Wi-Fi in all areas", "connectivity", 1),
            ("24-hour concierge & tour desk", "service", 1),
        ],
    },

    "movenpick jolie": {
        "description": (
            "A lush garden resort on Luxor's east bank, Mövenpick Jolie Ville "
            "Luxor sits on its own island in the Nile — reachable only via the "
            "hotel's private causeway. Bungalow-style rooms spread across "
            "flowering gardens, with pools, restaurants, and a spa nestled "
            "between them. The hotel runs three outdoor pools, two tennis "
            "courts, and a wellness centre; its restaurants range from Egyptian "
            "buffet to à la carte Italian and international. The resort's "
            "island setting means exceptional quiet, yet Karnak Temple is "
            "only a 10-minute shuttle away."
        ),
        "neighborhood": (
            "On King's Island, a private island in the Nile at Luxor. The hotel "
            "runs a 24-hour causeway shuttle to the east bank. Karnak Temple and "
            "Luxor Museum are 10-15 minutes away; Luxor Temple and the ferry to "
            "the West Bank are 15 minutes. Luxor International Airport is 15 "
            "minutes by car."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "The causeway shuttle operates 24 hours.\n"
            "No smoking inside bungalows.\n"
            "Children welcome; kids' activities provided.\n"
            "Quiet hours 23:00 – 06:00."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged the first night. Non-refundable rates charged in full."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival. The "
            "causeway shuttle is available from the hotel gate — allow extra "
            "10 minutes for arrivals and departures."
        ),
        "tips": (
            "Book a bungalow facing the Nile — you can watch feluccas sail past.\n"
            "The hotel's causeway shuttle runs 24 hours — very handy for early tours.\n"
            "Try the Egyptian buffet night — excellent value.\n"
            "Tennis courts are free — book at reception.\n"
            "Bring a torch for walking between bungalows after dark."
        ),
        "facilities": [
            ("Three outdoor pools", "pool", 3),
            ("Full spa & wellness centre", "spa", 1),
            ("Multiple restaurants + poolside bar", "dining", 3),
            ("Two tennis courts", "sport", 2),
            ("Private island location on the Nile", "beach", 1),
            ("Kids' club & children's activities", "family", 1),
            ("24-hour causeway shuttle", "transport", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    #  SHERATON (1 property)
    # ═══════════════════════════════════════════════════════════════
    "sheraton hotel luxor": {
        "description": (
            "A long-standing landmark on Luxor's Nile corniche, Sheraton Luxor "
            "combines classic hospitality with modern comfort. Rooms overlook "
            "either the river or the hotel's mature gardens, and the rooftop "
            "restaurant offers one of the best sunset views in the city — with "
            "the illuminated Luxor Temple glowing in the distance. The hotel's "
            "pool area is generous, its fitness centre well-equipped, and its "
            "spa offers traditional Egyptian treatments. Well-positioned for "
            "both temple visits and Nile cruise departures."
        ),
        "neighborhood": (
            "On the Nile corniche, walking distance to Luxor Temple, the Luxor "
            "Museum, and the winter palace gardens. Karnak Temple is a short "
            "taxi ride north; the West Bank ferry is 10 minutes away. Luxor "
            "International Airport is 15 minutes by car."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Rooftop restaurant reservations recommended in high season.\n"
            "Children welcome.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival for "
            "incidentals. Airport transfers can be arranged in advance."
        ),
        "tips": (
            "Rooftop restaurant is best at sunset — reserve ahead.\n"
            "Ask for a Nile-view room on a high floor.\n"
            "The hotel can arrange private Egyptologist guides.\n"
            "Book the hot-air balloon flight through the concierge — better rates than the street.\n"
            "The buffet breakfast is generous — arrive early."
        ),
        "facilities": [
            ("Riverside outdoor pool & sun terrace", "pool", 1),
            ("Two restaurants including rooftop", "dining", 2),
            ("Fitness centre", "sport", 1),
            ("Spa & massage services", "spa", 1),
            ("Meeting & event rooms", "business", 2),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    #  SONESTA (3 properties)
    # ═══════════════════════════════════════════════════════════════
    "sonesta st gorge": {
        "description": (
            "A contemporary Nile-front hotel in the heart of Luxor, Sonesta "
            "St George offers modern rooms with river or city views, an outdoor "
            "pool with sun terrace, and quick access to Luxor Temple and the "
            "souk. The hotel's restaurant serves Egyptian and international "
            "cuisine; a lobby bar and poolside café handle lighter fare. Popular "
            "with both tour groups and independent travellers wanting a "
            "comfortable, well-located base for temple tours and Nile cruises."
        ),
        "neighborhood": (
            "Central Luxor, a short walk from Luxor Temple and the Luxor Museum. "
            "The train station is 10 minutes away, and the West Bank ferry is "
            "5 minutes on foot. Luxor International Airport is 15 minutes by car."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival for incidentals."
        ),
        "tips": (
            "Breakfast on the Nile-facing terrace is worth getting up for.\n"
            "The hotel can arrange hot-air balloon rides at dawn.\n"
            "Ask about the shuttle to Karnak — saves on taxi fares.\n"
            "Try the rooftop for sunset drinks — best view in the hotel."
        ),
        "facilities": [
            ("Outdoor pool with sun terrace", "pool", 1),
            ("Two restaurants + bar", "dining", 3),
            ("Fitness centre", "sport", 1),
            ("Business centre", "business", 1),
            ("Free Wi-Fi in rooms & public areas", "connectivity", 1),
        ],
    },

    "sonesta pharaoh": {
        "description": (
            "A well-established Red Sea resort in Hurghada, Sonesta Pharaoh "
            "Beach combines comfortable rooms with direct beach access and a "
            "wide range of water sports. Multiple pools, several restaurants, "
            "and an on-site dive centre make it a favourite for both families "
            "and divers. The hotel's gardens are mature, its private beach "
            "spacious, and the house reef good for snorkelling."
        ),
        "neighborhood": (
            "On the Hurghada seafront, about 15 minutes from the airport and "
            "10 minutes from the marina. Giftun Island dive sites are 45 "
            "minutes by boat."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival."
        ),
        "tips": (
            "Snorkelling from the hotel beach is excellent at high tide.\n"
            "The dive centre offers PADI courses at competitive rates.\n"
            "Book a sea-view room for the best Red Sea sunsets.\n"
            "The Italian restaurant on-site is worth booking."
        ),
        "facilities": [
            ("Private beach with sun loungers", "beach", 1),
            ("Two outdoor pools", "pool", 2),
            ("Dive centre & water sports", "sport", 2),
            ("Multiple restaurants + bars", "dining", 3),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    "sonesta beach resort taba": {
        "description": (
            "Perched between the Sinai mountains and the Gulf of Aqaba, Sonesta "
            "Beach Resort Taba offers a quieter alternative to Sharm's busier "
            "resorts. The hotel's private beach, three pools, and dive centre "
            "make the most of its exceptional location — with the reefs of the "
            "Gulf of Aqaba just offshore and the border with Israel a short "
            "drive away. Popular for both family holidays and dive trips."
        ),
        "neighborhood": (
            "On the Gulf of Aqaba coast at Taba, close to the Israeli border. "
            "The hotel is roughly 45 minutes from Sharm El Sheikh airport and "
            "30 minutes from the resorts of Aqaba. Some of the best dive sites "
            "in the northern Red Sea are within easy boat range."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival. Border "
            "crossing to Israel requires advance notice — ask the concierge."
        ),
        "tips": (
            "The dive sites in the Gulf of Aqaba are spectacular — book early.\n"
            "Ask for a sea-view room for the sunset.\n"
            "Bring a light layer — Taba evenings can be breezy.\n"
            "Snorkelling from the hotel beach is excellent."
        ),
        "facilities": [
            ("Three outdoor pools", "pool", 3),
            ("Private beach", "beach", 1),
            ("Dive centre & water sports", "sport", 2),
            ("Multiple restaurants + bars", "dining", 3),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },
        # ═══════════════════════════════════════════════════════════════
    #  MARRIOTT (3 properties)
    # ═══════════════════════════════════════════════════════════════
    "hurghada marriott": {
        "description": (
            "Set on a private stretch of Red Sea beach in the heart of Hurghada, "
            "the Hurghada Marriott Beach Resort offers polished rooms, a generous "
            "pool complex, and a variety of dining options. Its central location "
            "puts guests within easy reach of the marina, the Sheraton Road "
            "shopping strip, and some of the best dive operators on the coast. "
            "The hotel's restaurants cover Italian, Asian, and Middle Eastern "
            "cuisine; the spa offers traditional treatments; and the beach "
            "handles water sports and reef snorkelling. A dependable, well-run "
            "five-star choice for both couples and families."
        ),
        "neighborhood": (
            "Central Hurghada, walking distance to the marina, Sheraton Road "
            "shops, and the seafront promenade. The airport is 15 minutes away, "
            "and the Giftun Island dive sites are 45 minutes by boat."
        ),
        "house_rules": (
            "Check-in from 15:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome; kids' club free for guests.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival for incidentals."
        ),
        "tips": (
            "Book a room in the main building for the best sea views.\n"
            "The breakfast buffet is extensive — arrive hungry.\n"
            "Use the concierge to book dives — they know the best operators.\n"
            "The Italian restaurant is the best on-site."
        ),
        "facilities": [
            ("Private beach with water sports", "beach", 1),
            ("Large pool complex", "pool", 2),
            ("Multiple restaurants + bars", "dining", 4),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi throughout", "connectivity", 1),
            ("24-hour concierge", "service", 1),
        ],
    },

    "marriott cairo": {
        "description": (
            "A landmark five-star hotel on the Nile in downtown Cairo, the "
            "Marriott Cairo Hotel & Omar Khayyam Casino blends modern rooms "
            "with lush gardens and a historic palace wing. Well-placed for "
            "visits to the Egyptian Museum, Khan el-Khalili bazaar, and the "
            "Pyramids of Giza, the hotel offers a wide range of restaurants, "
            "a full-service spa, and an outdoor pool set in beautiful gardens. "
            "The palace wing, with its colonnaded façade and grand ballroom, "
            "is a destination in itself — a piece of 19th-century Cairo "
            "preserved at the heart of the modern city."
        ),
        "neighborhood": (
            "On the Nile in Zamalek, walking distance to the Opera House and "
            "the Egyptian Museum. Cairo International Airport is 30-45 minutes "
            "by car, depending on traffic. Khan el-Khalili bazaar is a 15-"
            "minute taxi ride; the Pyramids of Giza are roughly 45 minutes "
            "southwest."
        ),
        "house_rules": (
            "Check-in from 15:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Formal dress code in some restaurants after 18:00.\n"
            "Children welcome.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged the first night. Non-refundable rates charged in full."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival for the "
            "stay plus incidentals. Airport transfers can be arranged — allow "
            "extra time for Cairo traffic."
        ),
        "tips": (
            "Ask for a Nile-view room — the Cairo skyline at night is spectacular.\n"
            "The historic palace wing has beautiful gardens for a quiet drink.\n"
            "Book the Pyramids tour with the concierge to avoid taxi haggling.\n"
            "Allow 60-90 minutes for the trip to Giza during rush hour.\n"
            "Try afternoon tea in the palace wing — a Cairo tradition."
        ),
        "facilities": [
            ("Outdoor pool set in gardens", "pool", 1),
            ("Multiple restaurants + bars", "dining", 5),
            ("Full-service spa", "spa", 1),
            ("Fitness centre", "sport", 1),
            ("Business centre & meeting rooms", "business", 4),
            ("Historic palace wing with ballroom", "other", 1),
            ("Free Wi-Fi throughout", "connectivity", 1),
        ],
    },

    "marriott red sea": {
        "description": (
            "Overlooking the Red Sea in the heart of Sharm El Sheikh, this "
            "Marriott resort combines sleek rooms with direct beach access "
            "and a beautifully landscaped pool area. The hotel's restaurants "
            "cover international, Italian, and seafood cuisine; its spa and "
            "fitness centre are modern; and the dive centre arranges trips to "
            "the finest reefs in the Ras Mohammed National Park. A convenient, "
            "well-serviced base for exploring Naama Bay's promenade and the "
            "shopping and entertainment venues nearby."
        ),
        "neighborhood": (
            "In Sharm El Sheikh near Naama Bay, about 15 minutes from the "
            "airport. Ras Mohammed National Park is a 40-minute drive. The "
            "shopping, restaurants, and nightlife of Naama Bay are within "
            "easy reach."
        ),
        "house_rules": (
            "Check-in from 15:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival."
        ),
        "tips": (
            "The hotel's private beach is quieter than Naama Bay's public beaches.\n"
            "Book snorkelling trips direct through the resort's dive centre.\n"
            "Dinner at the beachside grill is excellent value.\n"
            "Ask for a sea-view room — the sunrise is worth waking for."
        ),
        "facilities": [
            ("Private beach", "beach", 1),
            ("Outdoor pool", "pool", 1),
            ("Multiple restaurants + bars", "dining", 3),
            ("Fitness centre & spa", "spa", 1),
            ("Dive centre", "sport", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi throughout", "connectivity", 1),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    #  FAIRMONT (1 property)
    # ═══════════════════════════════════════════════════════════════
    "fairmont nile city": {
        "description": (
            "A sleek, contemporary five-star tower on the Nile in downtown "
            "Cairo, Fairmont Nile City offers panoramic river views, "
            "exceptional dining, and one of the city's best rooftop bars. "
            "The hotel's rooms and suites are among the largest in Cairo, "
            "with floor-to-ceiling windows framing the river and the city "
            "skyline. Its restaurants span Japanese, Italian, and Middle "
            "Eastern cuisine; the rooftop pool and bar are a destination "
            "in themselves; and the spa offers hammam and modern wellness "
            "treatments. Perfect for business travellers and couples who "
            "want luxury convenience close to the Egyptian Museum and Khan "
            "el-Khalili."
        ),
        "neighborhood": (
            "On the Nile in the Ramlet Boulaq district, 5 minutes from "
            "Tahrir Square and the Egyptian Museum. Cairo International "
            "Airport is 30-45 minutes by car. The Opera House and Zamalek "
            "district are 15 minutes north."
        ),
        "house_rules": (
            "Check-in from 15:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Rooftop bar has a smart-casual dress code after 18:00.\n"
            "Children welcome.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged the first night. Non-refundable rates charged in full."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation of the stay plus "
            "incidentals is taken on arrival. Rooftop reservations recommended "
            "for sunset."
        ),
        "tips": (
            "Book a Nile-view room on a high floor for the best panorama.\n"
            "The rooftop bar is a destination in itself — reserve for sunset.\n"
            "Ask the concierge about private Giza pyramid tours at dawn.\n"
            "Try the Japanese restaurant — one of Cairo's best.\n"
            "Allow extra time for airport transfers — Cairo traffic is legendary."
        ),
        "facilities": [
            ("Rooftop pool with Nile views", "pool", 1),
            ("Multiple fine-dining restaurants", "dining", 4),
            ("Full-service spa & hammam", "spa", 1),
            ("Fitness centre", "sport", 1),
            ("Business centre & meeting rooms", "business", 4),
            ("Rooftop bar & lounge", "dining", 1),
            ("Free Wi-Fi throughout", "connectivity", 1),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    #  KEMPINSKI (1 property)
    # ═══════════════════════════════════════════════════════════════
    "kempinski soma": {
        "description": (
            "An exclusive Red Sea retreat on the pristine shores of Soma Bay, "
            "Kempinski Hotel Soma Bay pairs European luxury with Egyptian "
            "warmth. The resort's own championship golf course, thalasso spa, "
            "and house reef make it a destination in its own right — perfect "
            "for couples, golfers, and discerning divers. Guest rooms and "
            "suites are among the most spacious on the Red Sea, with private "
            "terraces overlooking the sea or the golf course. Four restaurants "
            "span Mediterranean, Oriental, and seafood cuisine; the thalasso "
            "spa is one of the best in Egypt."
        ),
        "neighborhood": (
            "In Soma Bay, a secluded peninsula about 45 minutes south of "
            "Hurghada International Airport. The resort is self-contained, "
            "with its own golf course and marina. Safaga, with its dive sites "
            "and fishing harbour, is 15 minutes away."
        ),
        "house_rules": (
            "Check-in from 15:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Golf course dress code: collared shirts, no denim.\n"
            "Children welcome; kids' club available.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 72 hours before check-in. Cancellations within "
            "72 hours are charged the first night. Non-refundable rates charged in full. "
            "Golf and spa packages have separate terms."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation of the stay plus "
            "incidentals on arrival. Golf tee times and spa treatments should "
            "be booked in advance during high season."
        ),
        "tips": (
            "The thalasso spa is the highlight — book the full-day ritual.\n"
            "The house reef is one of the best in the Red Sea — bring an underwater camera.\n"
            "Rent a golf cart to explore the peninsula — beautiful at sunset.\n"
            "Book tee times well ahead — the course is popular with members.\n"
            "Try the seafood restaurant — the catch is locally sourced."
        ),
        "facilities": [
            ("Private beach with house reef", "beach", 1),
            ("Multiple outdoor pools", "pool", 3),
            ("Championship 18-hole golf course", "sport", 1),
            ("Thalasso spa & wellness centre", "spa", 1),
            ("Four restaurants + bars", "dining", 5),
            ("Kids' club", "family", 1),
            ("Fitness centre", "sport", 1),
            ("Free Wi-Fi throughout", "connectivity", 1),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    #  RADISSON (2 properties)
    # ═══════════════════════════════════════════════════════════════
    "radisson blu sharm": {
        "description": (
            "A relaxed resort in the Ras Um Sid area of Sharm El Sheikh, "
            "Radisson Blu Resort offers comfortable rooms, two large pools, "
            "and easy access to some of the best snorkelling on the Sinai "
            "coast. The reef at Ras Um Sid — a short walk from the hotel — "
            "is one of the finest shore dives in the Red Sea. The hotel's "
            "restaurants cover international and Middle Eastern cuisine, and "
            "the spa offers a range of treatments. A solid choice for "
            "families and divers looking for value without compromising on "
            "quality."
        ),
        "neighborhood": (
            "In Ras Um Sid, 10 minutes from Naama Bay and 20 minutes from "
            "Sharm El Sheikh airport. The reef at Ras Um Sid is walking "
            "distance from the hotel. Il Mercato shopping mall is 15 "
            "minutes away."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome; kids' club available.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival."
        ),
        "tips": (
            "The nearby Ras Um Sid reef is superb for shore diving.\n"
            "Ask for a pool-view room with a balcony — great for evening drinks.\n"
            "The hotel runs a free shuttle to Naama Bay several times a day.\n"
            "Snorkelling from the hotel's beach is best in the morning."
        ),
        "facilities": [
            ("Two outdoor pools", "pool", 2),
            ("Private beach & reef access", "beach", 1),
            ("Dive centre", "sport", 1),
            ("Restaurant + pool bar", "dining", 2),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    "radisson blu resort taba": {
        "description": (
            "Set between the Sinai mountains and the Gulf of Aqaba, Radisson "
            "Blu Resort Taba offers a serene escape with exceptional diving "
            "just offshore. The hotel's private beach, multiple pools, and "
            "spa make the most of its dramatic setting — the desert cliffs "
            "rise on one side, the blue waters of the Gulf on the other. "
            "Restaurants serve international and local cuisine, and the "
            "dive centre arranges trips to some of the finest reefs in the "
            "region."
        ),
        "neighborhood": (
            "On the Gulf of Aqaba coast at Taba, close to the Israeli border. "
            "About 45 minutes from Sharm El Sheikh airport and 30 minutes from "
            "the resorts of Aqaba. Some of the best dive sites in the northern "
            "Red Sea are within easy boat range."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival. Border "
            "crossing to Israel can be arranged — ask the concierge."
        ),
        "tips": (
            "The dive sites in the Gulf of Aqaba are spectacular — book early.\n"
            "Ask for a sea-view room for the sunrise over the mountains.\n"
            "Bring a light layer — Taba evenings are breezier than Sharm.\n"
            "Snorkelling from the hotel beach is excellent at high tide."
        ),
        "facilities": [
            ("Private beach", "beach", 1),
            ("Multiple outdoor pools", "pool", 3),
            ("Dive centre & water sports", "sport", 2),
            ("Multiple restaurants + bars", "dining", 3),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    #  RITZ-CARLTON (1 property)
    # ═══════════════════════════════════════════════════════════════
    "ritz carlton sharm": {
        "description": (
            "One of the Sinai's most luxurious resorts, The Ritz-Carlton "
            "Sharm El Sheikh sits on a private beach amid landscaped "
            "gardens on the Ras Um Sid headland. Elegant rooms, an award-"
            "winning spa, and impeccable service make it a popular choice "
            "for honeymooners and travellers celebrating special "
            "occasions. The hotel's signature restaurant offers fine dining "
            "with a view, the pool terraces are peaceful, and the house "
            "reef is superb for snorkelling right off the beach. Every "
            "detail — from the Egyptian-cotton linens to the personalised "
            "concierge service — reflects the Ritz-Carlton standard."
        ),
        "neighborhood": (
            "On the Ras Um Sid headland, 10 minutes from Naama Bay and 20 "
            "minutes from Sharm El Sheikh airport. Some of the best reefs "
            "in the Red Sea are within easy reach, including Ras Um Sid "
            "and Ras Mohammed National Park."
        ),
        "house_rules": (
            "Check-in from 15:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Formal dress code in signature restaurant after 18:00.\n"
            "Children welcome; kids' club available.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 72 hours before check-in. Cancellations "
            "within 72 hours are charged the first night. Non-refundable rates "
            "charged in full. Peak periods (Christmas, New Year, Easter) have "
            "stricter policies."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation of the stay plus "
            "incidentals on arrival. Butler service available in suites. "
            "Airport transfers can be arranged through the concierge."
        ),
        "tips": (
            "Book a sea-view suite for the best experience.\n"
            "The hotel's signature restaurant is excellent — reserve in advance.\n"
            "Snorkelling right off the hotel beach is superb.\n"
            "Ask about the private dinner on the beach — unforgettable for special occasions.\n"
            "The spa's signature treatment is worth the splurge."
        ),
        "facilities": [
            ("Private beach with house reef", "beach", 1),
            ("Three outdoor pools", "pool", 3),
            ("Signature spa & hammam", "spa", 1),
            ("Multiple restaurants + bars", "dining", 5),
            ("Fitness centre", "sport", 1),
            ("Kids' club", "family", 1),
            ("Butler service in suites", "service", 1),
            ("Free Wi-Fi throughout", "connectivity", 1),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    #  JAZ (2 properties)
    # ═══════════════════════════════════════════════════════════════
    "jaz belvedere": {
        "description": (
            "A stylish 5-star resort in the Montazah area of Sharm El "
            "Sheikh, Jaz Belvedere offers contemporary rooms, extensive "
            "pool areas, and direct access to a beautiful house reef. The "
            "hotel's modern architecture and lush gardens create a relaxed, "
            "upscale atmosphere; its restaurants cover international, "
            "Italian, and Oriental cuisine; and the dive centre arranges "
            "trips to the best reefs in the area. A great choice for "
            "couples and families who want a modern, well-run Red Sea "
            "holiday."
        ),
        "neighborhood": (
            "In the Montazah district of Sharm El Sheikh, 10 minutes from "
            "the airport and 15 minutes from Naama Bay. The hotel's own "
            "house reef is accessible directly from the beach."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome; kids' club available.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations within "
            "48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival."
        ),
        "tips": (
            "The house reef is one of the best on the Sinai coast.\n"
            "Book a swim-up pool room for the ultimate relaxation.\n"
            "The Italian à la carte restaurant is worth booking.\n"
            "Snorkel early in the morning for the best visibility."
        ),
        "facilities": [
            ("Multiple outdoor pools", "pool", 4),
            ("Private beach with house reef", "beach", 1),
            ("Dive centre", "sport", 1),
            ("Multiple restaurants + bars", "dining", 4),
            ("Spa & wellness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    "jaz mirabel": {
        "description": (
            "A large, contemporary resort on the Red Sea coast at Sharm El "
            "Sheikh, Jaz Mirabel Club Resort offers extensive pools, a "
            "private beach, and a full range of facilities for families. "
            "The hotel's gardens are lush, its restaurants varied, and its "
            "animation programme lively. The house reef is accessible from "
            "the beach, and the dive centre arranges trips to the finest "
            "reefs in the area."
        ),
        "neighborhood": (
            "In the Nabq Bay area of Sharm El Sheikh, 10 minutes from the "
            "airport. The hotel is close to the Nabq nature reserve and "
            "within easy reach of Naama Bay and the airport."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome; kids' club available.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations "
            "within 48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival."
        ),
        "tips": (
            "Book a family room for extra space.\n"
            "The animation team runs excellent evening shows.\n"
            "The house reef is excellent for snorkelling.\n"
            "Book a Nabq nature reserve tour through the concierge."
        ),
        "facilities": [
            ("Multiple outdoor pools", "pool", 4),
            ("Private beach with house reef", "beach", 1),
            ("Dive centre", "sport", 1),
            ("Multiple restaurants + bars", "dining", 4),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    #  IBEROTEL (3 properties)
    # ═══════════════════════════════════════════════════════════════
    "iberotel aquamarine": {
        "description": (
            "A large, modern resort on the Hurghada seafront, Iberotel "
            "Aquamarine offers extensive pools, a private beach, and a "
            "comprehensive all-inclusive programme. Popular with families "
            "and couples who want variety and easy access to the marina, "
            "the hotel runs multiple restaurants, a spa, and an "
            "entertainment programme that spans everything from aqua "
            "aerobics to evening shows. The hotel's gardens are lush, and "
            "its private beach is well-equipped with sun loungers and "
            "shade."
        ),
        "neighborhood": (
            "On the Hurghada promenade, 10 minutes from the marina and 15 "
            "minutes from the airport. Sheraton Road shopping is a 5-minute "
            "walk."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "All-inclusive wristbands must be worn on-site.\n"
            "Children welcome; kids' club free for guests.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations "
            "within 48 hours are charged one night. Non-refundable rates charged "
            "in full."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival for "
            "incidentals. All-inclusive wristbands issued at check-in."
        ),
        "tips": (
            "Book a sea-view room for the best sunsets.\n"
            "The à la carte restaurants are included in the all-inclusive rate.\n"
            "The hotel's animation team runs excellent evening shows.\n"
            "Snorkelling from the beach is best at high tide."
        ),
        "facilities": [
            ("Multiple outdoor pools", "pool", 4),
            ("Private beach", "beach", 1),
            ("Multiple restaurants + bars", "dining", 5),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Animation & evening entertainment", "other", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    "iberotel club fanar": {
        "description": (
            "On the Red Sea coast north of Hurghada, Iberotel Club Fanar "
            "offers a relaxed, all-inclusive resort experience with a "
            "strong focus on water sports and diving. The hotel's own house "
            "reef is excellent for snorkelling; multiple pools and "
            "restaurants cover all the essentials; and the animation team "
            "keeps children and adults entertained. A solid choice for "
            "families and divers looking for value."
        ),
        "neighborhood": (
            "North of Hurghada, about 20 minutes from the airport and 15 "
            "minutes from the marina. The hotel's house reef is one of the "
            "better ones in the area."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations "
            "within 48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival."
        ),
        "tips": (
            "The house reef is excellent for snorkelling — bring an underwater camera.\n"
            "Book a sea-view room for the sunsets.\n"
            "Try the beachside grill — best value on-site."
        ),
        "facilities": [
            ("Multiple outdoor pools", "pool", 3),
            ("Private beach with house reef", "beach", 1),
            ("Dive centre", "sport", 1),
            ("Multiple restaurants + bars", "dining", 3),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    "iberotel makadi saraya": {
        "description": (
            "Set within the landscaped grounds of Makadi Bay, Iberotel "
            "Makadi Saraya Palms offers a relaxed, garden-style resort "
            "experience on the Red Sea. The hotel's pools, restaurants, "
            "and spa are surrounded by lush greenery; its private beach is "
            "a short walk away. Popular with couples and families looking "
            "for a quieter alternative to central Hurghada."
        ),
        "neighborhood": (
            "In Makadi Bay, about 30 minutes south of Hurghada airport. The "
            "bay itself is sheltered and calm, ideal for swimming, snorkelling, "
            "and beginner dives."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations "
            "within 48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival."
        ),
        "tips": (
            "Makadi Bay is calm and sheltered — great for beginner snorkellers.\n"
            "Book a garden-view room — cooler in the summer.\n"
            "Try the dive centre for a guided reef trip."
        ),
        "facilities": [
            ("Multiple outdoor pools", "pool", 3),
            ("Private beach", "beach", 1),
            ("Dive centre", "sport", 1),
            ("Multiple restaurants + bars", "dining", 3),
            ("Spa & wellness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    #  TITANIC (2 properties)
    # ═══════════════════════════════════════════════════════════════
    "titanic palace": {
        "description": (
            "One of the largest resorts in Hurghada, Titanic Palace & Aqua "
            "Park combines sprawling pools, an on-site water park, and a "
            "private beach — ideal for families with children and "
            "travellers who love a lively all-inclusive atmosphere. The "
            "hotel's water park features multiple slides and a lazy river; "
            "its restaurants span everything from Italian to Asian; and its "
            "animation team runs a full programme of activities and evening "
            "shows. A great choice for families who want variety without "
            "leaving the resort."
        ),
        "neighborhood": (
            "On the Hurghada coast, 15 minutes from the airport and 20 "
            "minutes from the marina. The hotel is self-contained, with "
            "shops, restaurants, and entertainment all on-site."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children must be supervised in the water park.\n"
            "All-inclusive wristbands must be worn on-site.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations "
            "within 48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival."
        ),
        "tips": (
            "The water park is a huge hit with kids — arrive early for the best spots.\n"
            "Book a family suite for extra space.\n"
            "Evening entertainment at the amphitheatre is worth catching.\n"
            "The à la carte restaurants are included — try them all."
        ),
        "facilities": [
            ("Water park with slides & lazy river", "family", 1),
            ("Multiple outdoor pools", "pool", 5),
            ("Private beach", "beach", 1),
            ("Several restaurants + bars", "dining", 6),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    "titanic beach spa": {
        "description": (
            "A lively, family-friendly resort on the Hurghada coast, Titanic "
            "Beach Spa & Aqua Park pairs extensive pools and a water park "
            "with direct beach access and a comprehensive all-inclusive "
            "programme. The hotel's spa is one of the largest in Hurghada, "
            "and its restaurants cover international and Oriental cuisine. "
            "Great for families who want variety and fun."
        ),
        "neighborhood": (
            "On the Hurghada coast, 15 minutes from the airport and 15 "
            "minutes from the marina."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children must be supervised in the water park.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations "
            "within 48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival."
        ),
        "tips": (
            "The spa is one of the best in Hurghada — book a hammam.\n"
            "Book a family room for extra space.\n"
            "Evening animation programme is worth catching."
        ),
        "facilities": [
            ("Water park with slides", "family", 1),
            ("Multiple outdoor pools", "pool", 4),
            ("Private beach", "beach", 1),
            ("Multiple restaurants + bars", "dining", 5),
            ("Full-service spa & hammam", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    #  PYRAMISA (3 properties)
    # ═══════════════════════════════════════════════════════════════
    "pyramisa isis luxor": {
        "description": (
            "A comfortable, well-priced hotel on the Nile in Luxor, Pyramisa "
            "Isis Luxor offers modern rooms, a riverside pool, and easy "
            "access to the temples. The hotel's rooftop pool is a "
            "particular highlight — with panoramic views across the Nile "
            "to the West Bank. Restaurants serve Egyptian and international "
            "cuisine; the concierge can arrange tours, guides, and hot-air "
            "balloon rides. A solid choice for travellers who want a good "
            "location without paying five-star rates."
        ),
        "neighborhood": (
            "Central Luxor, walking distance to Luxor Temple and the Luxor "
            "Museum. The train station is 10 minutes away, and the West "
            "Bank ferry is 5 minutes."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations "
            "within 48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival."
        ),
        "tips": (
            "Ask for a Nile-facing room — the view is worth the small premium.\n"
            "The rooftop pool is a great spot after a day of sightseeing.\n"
            "The hotel can arrange hot-air balloon rides at dawn.\n"
            "Book the Karnak Sound & Light show through the concierge."
        ),
        "facilities": [
            ("Rooftop pool with Nile views", "pool", 1),
            ("Restaurant + bar", "dining", 2),
            ("Fitness centre", "sport", 1),
            ("Rooftop terrace", "other", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    "pyramisa cairo": {
        "description": (
            "In the Dokki district of Cairo, close to the Nile and the "
            "Egyptian Museum, Pyramisa Cairo offers comfortable rooms, "
            "multiple dining options, and easy access to the city's main "
            "sights. The hotel's restaurants cover Egyptian, Chinese, and "
            "international cuisine; the rooftop pool offers views across "
            "the Nile; and the hotel's location makes it a good base for "
            "exploring Cairo's museums, markets, and the Pyramids at Giza."
        ),
        "neighborhood": (
            "In Dokki, walking distance to the Nile and 10 minutes by taxi "
            "to Tahrir Square and the Egyptian Museum. The Pyramids of Giza "
            "are roughly 40 minutes southwest; Cairo International Airport "
            "is 45 minutes northeast."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations "
            "within 48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival."
        ),
        "tips": (
            "Ask for a Nile-side room.\n"
            "Use the hotel's taxis for sightseeing — better rates than hailing.\n"
            "The buffet dinner is generous and good value.\n"
            "Book the Pyramids tour early — traffic can be heavy."
        ),
        "facilities": [
            ("Outdoor pool with Nile views", "pool", 1),
            ("Multiple restaurants + bars", "dining", 2),
            ("Fitness centre", "sport", 1),
            ("Business centre", "business", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    "pyramisa blue lagoon": {
        "description": (
            "A relaxed resort on the Red Sea coast at Hurghada, Pyramisa "
            "Blue Lagoon Resort offers a lagoon-style pool, private beach, "
            "and comfortable rooms. The hotel's restaurants cover "
            "international and Egyptian cuisine; the dive centre arranges "
            "trips to the nearby reefs; and the animation programme keeps "
            "the atmosphere lively. A solid value choice for families and "
            "couples."
        ),
        "neighborhood": (
            "On the Hurghada coast, about 20 minutes from the airport. The "
            "hotel is close to the marina and the dive sites of Giftun "
            "Island."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations "
            "within 48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival."
        ),
        "tips": (
            "The lagoon pool is a highlight — get there early for the best spots.\n"
            "Book a sea-view room for the best sunsets.\n"
            "The dive centre arranges trips to Giftun Island — highly recommended."
        ),
        "facilities": [
            ("Lagoon-style pool", "pool", 2),
            ("Private beach", "beach", 1),
            ("Dive centre", "sport", 1),
            ("Multiple restaurants + bars", "dining", 3),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    #  STEIGENBERGER (1 property)
    # ═══════════════════════════════════════════════════════════════
    "steigenberger nile palace": {
        "description": (
            "On the Nile corniche in Luxor, Steigenberger Nile Palace "
            "combines German precision with Egyptian warmth. Elegant rooms, "
            "excellent restaurants, and a riverside pool terrace make it one "
            "of the city's most polished stays — perfect for temple tours "
            "and Nile cruise departures. The hotel's restaurants serve "
            "Mediterranean, Oriental, and international cuisine; the spa "
            "offers traditional hammam and modern treatments; and the "
            "concierge can arrange private Egyptologist guides, hot-air "
            "balloon flights, and day trips to the temples."
        ),
        "neighborhood": (
            "On the Nile in central Luxor, a short walk to the Luxor Museum "
            "and the Luxor Temple. Karnak is 10 minutes by taxi; the West "
            "Bank ferry is 10 minutes away. Luxor International Airport is "
            "15 minutes by car."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Formal dress code in the à la carte restaurant after 18:00.\n"
            "Children welcome.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations "
            "within 48 hours are charged one night. Non-refundable rates charged "
            "in full."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival."
        ),
        "tips": (
            "The Nile-view rooms are worth the upgrade.\n"
            "Book the Egyptian restaurant for a genuine taste of local cuisine.\n"
            "Ask about private guides — the concierge can arrange Egyptologists.\n"
            "The riverside pool terrace is lovely for afternoon tea."
        ),
        "facilities": [
            ("Riverside outdoor pool", "pool", 1),
            ("Multiple restaurants + bar", "dining", 3),
            ("Full-service spa & hammam", "spa", 1),
            ("Fitness centre", "sport", 1),
            ("Business centre", "business", 1),
            ("Free Wi-Fi throughout", "connectivity", 1),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    #  SAVOY (1 property)
    # ═══════════════════════════════════════════════════════════════
    "the savoy": {
        "description": (
            "A landmark hotel in the heart of Sharm El Sheikh, The Savoy is "
            "known for its elegant rooms, mature gardens, and prime position "
            "close to Naama Bay. Its long-standing reputation for service "
            "makes it a favourite with return guests. Multiple restaurants "
            "cover Italian, Oriental, and international cuisine; the pools "
            "and private beach are well-equipped; and the spa offers a "
            "range of treatments. A comfortable, well-run choice for both "
            "couples and families."
        ),
        "neighborhood": (
            "5 minutes from Naama Bay and 15 minutes from Sharm El Sheikh "
            "airport. The famous Il Mercato shopping mall is nearby, and "
            "the promenade's restaurants and nightlife are within easy "
            "reach."
        ),
        "house_rules": (
            "Check-in from 14:00, check-out by 12:00.\n"
            "No smoking inside guest rooms.\n"
            "Children welcome; kids' club available.\n"
            "Pets not permitted."
        ),
        "cancellation": (
            "Free cancellation up to 48 hours before check-in. Cancellations "
            "within 48 hours are charged one night."
        ),
        "check_in_details": (
            "Valid passport required. Card pre-authorisation on arrival."
        ),
        "tips": (
            "The gardens are wonderful for an evening stroll.\n"
            "Book a sea-view room for the best experience.\n"
            "The hotel's Italian restaurant is a Sharm institution.\n"
            "The tennis courts are free — book at reception."
        ),
        "facilities": [
            ("Two outdoor pools", "pool", 2),
            ("Private beach", "beach", 1),
            ("Multiple restaurants + bars", "dining", 4),
            ("Spa & fitness centre", "spa", 1),
            ("Tennis courts", "sport", 2),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },
    "hurghada marriott": {
        "description": "Set on a private stretch of Red Sea beach in the heart of Hurghada, the Hurghada Marriott Beach Resort offers polished rooms, a generous pool complex, and a variety of dining options. Its central location puts guests within easy reach of the marina, the Sheraton Road shopping strip, and some of the best dive operators on the coast.",
        "neighborhood": "Central Hurghada, walking distance to the marina, Sheraton Road shops, and the seafront promenade.",
        "house_rules": "Check-in from 15:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.\nPets not permitted.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "Book a room in the main building for the best sea views.\nThe breakfast buffet is extensive.\nUse the concierge to book dives.",
        "facilities": [
            ("Private beach with water sports", "beach", 1),
            ("Large pool complex", "pool", 2),
            ("Multiple restaurants + bars", "dining", 4),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi throughout", "connectivity", 1),
        ],
    },
    "marriott cairo": {
        "description": "A landmark five-star hotel on the Nile in downtown Cairo, the Marriott Cairo Hotel & Omar Khayyam Casino blends modern rooms with lush gardens and a historic palace wing.",
        "neighborhood": "On the Nile in Zamalek, walking distance to the Opera House and the Egyptian Museum.",
        "house_rules": "Check-in from 15:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "Ask for a Nile-view room.\nThe historic palace wing has beautiful gardens.\nBook the Pyramids tour with the concierge.",
        "facilities": [
            ("Outdoor pool set in gardens", "pool", 1),
            ("Multiple restaurants + bars", "dining", 5),
            ("Full-service spa", "spa", 1),
            ("Fitness centre", "sport", 1),
            ("Business centre & meeting rooms", "business", 4),
            ("Free Wi-Fi throughout", "connectivity", 1),
        ],
    },
    "marriott red sea": {
        "description": "Overlooking the Red Sea in the heart of Sharm El Sheikh, this Marriott resort combines sleek rooms with direct beach access and a beautifully landscaped pool area.",
        "neighborhood": "In Sharm El Sheikh near Naama Bay, about 15 minutes from the airport.",
        "house_rules": "Check-in from 15:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "The hotel's private beach is quieter than Naama Bay's public beaches.\nBook snorkelling trips direct through the resort's dive centre.",
        "facilities": [
            ("Private beach", "beach", 1),
            ("Outdoor pool", "pool", 1),
            ("Multiple restaurants + bars", "dining", 3),
            ("Fitness centre & spa", "spa", 1),
            ("Dive centre", "sport", 1),
            ("Free Wi-Fi throughout", "connectivity", 1),
        ],
    },
    "fairmont nile city": {
        "description": "A sleek, contemporary five-star tower on the Nile in downtown Cairo, Fairmont Nile City offers panoramic river views, exceptional dining, and one of the city's best rooftop bars.",
        "neighborhood": "On the Nile in the Ramlet Boulaq district, 5 minutes from Tahrir Square.",
        "house_rules": "Check-in from 15:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "Book a Nile-view room on a high floor.\nThe rooftop bar is a destination in itself.\nTry the Japanese restaurant.",
        "facilities": [
            ("Rooftop pool with Nile views", "pool", 1),
            ("Multiple fine-dining restaurants", "dining", 4),
            ("Full-service spa & hammam", "spa", 1),
            ("Fitness centre", "sport", 1),
            ("Business centre", "business", 4),
            ("Free Wi-Fi throughout", "connectivity", 1),
        ],
    },
    "kempinski soma": {
        "description": "An exclusive Red Sea retreat on the pristine shores of Soma Bay, Kempinski Hotel Soma Bay pairs European luxury with Egyptian warmth.",
        "neighborhood": "In Soma Bay, a secluded peninsula about 45 minutes south of Hurghada airport.",
        "house_rules": "Check-in from 15:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 72 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "The thalasso spa is the highlight.\nThe house reef is one of the best in the Red Sea.\nRent a golf cart to explore the peninsula.",
        "facilities": [
            ("Private beach with house reef", "beach", 1),
            ("Multiple outdoor pools", "pool", 3),
            ("Championship golf course", "sport", 1),
            ("Thalasso spa & wellness centre", "spa", 1),
            ("Four restaurants + bars", "dining", 5),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi throughout", "connectivity", 1),
        ],
    },
    "radisson blu sharm": {
        "description": "A relaxed resort in the Ras Um Sid area of Sharm El Sheikh, Radisson Blu Resort offers comfortable rooms, two large pools, and easy access to some of the best snorkelling on the Sinai coast.",
        "neighborhood": "In Ras Um Sid, 10 minutes from Naama Bay.",
        "house_rules": "Check-in from 14:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "The nearby Ras Um Sid reef is superb for shore diving.\nThe hotel runs a free shuttle to Naama Bay.",
        "facilities": [
            ("Two outdoor pools", "pool", 2),
            ("Private beach & reef access", "beach", 1),
            ("Dive centre", "sport", 1),
            ("Restaurant + pool bar", "dining", 2),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },
    "radisson blu resort taba": {
        "description": "Set between the Sinai mountains and the Gulf of Aqaba, Radisson Blu Resort Taba offers a serene escape with exceptional diving just offshore.",
        "neighborhood": "On the Gulf of Aqaba coast at Taba, close to the Israeli border.",
        "house_rules": "Check-in from 14:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "The dive sites in the Gulf of Aqaba are spectacular.\nAsk for a sea-view room for the sunrise.",
        "facilities": [
            ("Private beach", "beach", 1),
            ("Multiple outdoor pools", "pool", 3),
            ("Dive centre & water sports", "sport", 2),
            ("Multiple restaurants + bars", "dining", 3),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },
    "ritz carlton sharm": {
        "description": "One of the Sinai's most luxurious resorts, The Ritz-Carlton Sharm El Sheikh sits on a private beach amid landscaped gardens on the Ras Um Sid headland.",
        "neighborhood": "On the Ras Um Sid headland, 10 minutes from Naama Bay.",
        "house_rules": "Check-in from 15:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 72 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "Book a sea-view suite.\nThe signature restaurant is excellent.\nSnorkelling off the beach is superb.",
        "facilities": [
            ("Private beach with house reef", "beach", 1),
            ("Three outdoor pools", "pool", 3),
            ("Signature spa & hammam", "spa", 1),
            ("Multiple restaurants + bars", "dining", 5),
            ("Fitness centre", "sport", 1),
            ("Kids' club", "family", 1),
            ("Butler service in suites", "service", 1),
        ],
    },
    "jaz belvedere": {
        "description": "A stylish 5-star resort in the Montazah area of Sharm El Sheikh, Jaz Belvedere offers contemporary rooms, extensive pool areas, and direct access to a beautiful house reef.",
        "neighborhood": "In the Montazah district of Sharm El Sheikh, 10 minutes from the airport.",
        "house_rules": "Check-in from 14:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "The house reef is one of the best on the Sinai coast.\nBook a swim-up pool room.",
        "facilities": [
            ("Multiple outdoor pools", "pool", 4),
            ("Private beach with house reef", "beach", 1),
            ("Dive centre", "sport", 1),
            ("Multiple restaurants + bars", "dining", 4),
            ("Spa & wellness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },
    "jaz mirabel": {
        "description": "A large, contemporary resort on the Red Sea coast at Sharm El Sheikh, Jaz Mirabel Club Resort offers extensive pools, a private beach, and a full range of facilities for families.",
        "neighborhood": "In the Nabq Bay area of Sharm El Sheikh, 10 minutes from the airport.",
        "house_rules": "Check-in from 14:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "Book a family room for extra space.\nThe animation team runs excellent evening shows.",
        "facilities": [
            ("Multiple outdoor pools", "pool", 4),
            ("Private beach with house reef", "beach", 1),
            ("Dive centre", "sport", 1),
            ("Multiple restaurants + bars", "dining", 4),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Free Wi-Fi in public areas", "connectivity", 1),
        ],
    },
    "iberotel aquamarine": {
        "description": "A large, modern resort on the Hurghada seafront, Iberotel Aquamarine offers extensive pools, a private beach, and a comprehensive all-inclusive programme.",
        "neighborhood": "On the Hurghada promenade, 10 minutes from the marina.",
        "house_rules": "Check-in from 14:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "Book a sea-view room for the best sunsets.\nThe à la carte restaurants are included in the all-inclusive rate.",
        "facilities": [
            ("Multiple outdoor pools", "pool", 4),
            ("Private beach", "beach", 1),
            ("Multiple restaurants + bars", "dining", 5),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
            ("Animation & evening entertainment", "other", 1),
        ],
    },
    "iberotel club fanar": {
        "description": "On the Red Sea coast north of Hurghada, Iberotel Club Fanar offers a relaxed, all-inclusive resort experience with a strong focus on water sports and diving.",
        "neighborhood": "North of Hurghada, about 20 minutes from the airport.",
        "house_rules": "Check-in from 14:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "The house reef is excellent for snorkelling.\nBook a sea-view room for the sunsets.",
        "facilities": [
            ("Multiple outdoor pools", "pool", 3),
            ("Private beach with house reef", "beach", 1),
            ("Dive centre", "sport", 1),
            ("Multiple restaurants + bars", "dining", 3),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
        ],
    },
    "titanic palace": {
        "description": "One of the largest resorts in Hurghada, Titanic Palace & Aqua Park combines sprawling pools, an on-site water park, and a private beach — ideal for families.",
        "neighborhood": "On the Hurghada coast, 15 minutes from the airport.",
        "house_rules": "Check-in from 14:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "The water park is a huge hit with kids.\nBook a family suite for extra space.",
        "facilities": [
            ("Water park with slides & lazy river", "family", 1),
            ("Multiple outdoor pools", "pool", 5),
            ("Private beach", "beach", 1),
            ("Several restaurants + bars", "dining", 6),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
        ],
    },
    "titanic beach spa": {
        "description": "A lively, family-friendly resort on the Hurghada coast, Titanic Beach Spa & Aqua Park pairs extensive pools and a water park with direct beach access.",
        "neighborhood": "On the Hurghada coast, 15 minutes from the airport.",
        "house_rules": "Check-in from 14:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "The spa is one of the best in Hurghada — book a hammam.\nBook a family room for extra space.",
        "facilities": [
            ("Water park with slides", "family", 1),
            ("Multiple outdoor pools", "pool", 4),
            ("Private beach", "beach", 1),
            ("Multiple restaurants + bars", "dining", 5),
            ("Full-service spa & hammam", "spa", 1),
            ("Kids' club", "family", 1),
        ],
    },
    "pyramisa isis luxor": {
        "description": "A comfortable, well-priced hotel on the Nile in Luxor, Pyramisa Isis Luxor offers modern rooms, a riverside pool, and easy access to the temples.",
        "neighborhood": "Central Luxor, walking distance to Luxor Temple.",
        "house_rules": "Check-in from 14:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "Ask for a Nile-facing room.\nThe rooftop pool is a great spot after sightseeing.",
        "facilities": [
            ("Rooftop pool with Nile views", "pool", 1),
            ("Restaurant + bar", "dining", 2),
            ("Fitness centre", "sport", 1),
            ("Rooftop terrace", "other", 1),
        ],
    },
    "pyramisa cairo": {
        "description": "In the Dokki district of Cairo, close to the Nile and the Egyptian Museum, Pyramisa Cairo offers comfortable rooms, multiple dining options, and easy access to the city's main sights.",
        "neighborhood": "In Dokki, walking distance to the Nile.",
        "house_rules": "Check-in from 14:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "Ask for a Nile-side room.\nThe buffet dinner is generous and good value.",
        "facilities": [
            ("Outdoor pool with Nile views", "pool", 1),
            ("Multiple restaurants + bars", "dining", 2),
            ("Fitness centre", "sport", 1),
            ("Business centre", "business", 1),
        ],
    },
    "pyramisa blue lagoon": {
        "description": "A relaxed resort on the Red Sea coast at Hurghada, Pyramisa Blue Lagoon Resort offers a lagoon-style pool, private beach, and comfortable rooms.",
        "neighborhood": "On the Hurghada coast, about 20 minutes from the airport.",
        "house_rules": "Check-in from 14:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "The lagoon pool is a highlight.\nBook a sea-view room for the best sunsets.",
        "facilities": [
            ("Lagoon-style pool", "pool", 2),
            ("Private beach", "beach", 1),
            ("Dive centre", "sport", 1),
            ("Multiple restaurants + bars", "dining", 3),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
        ],
    },
    "steigenberger nile palace": {
        "description": "On the Nile corniche in Luxor, Steigenberger Nile Palace combines German precision with Egyptian warmth. Elegant rooms, excellent restaurants, and a riverside pool terrace make it one of the city's most polished stays.",
        "neighborhood": "On the Nile in central Luxor, a short walk to the Luxor Museum.",
        "house_rules": "Check-in from 14:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "The Nile-view rooms are worth the upgrade.\nBook the Egyptian restaurant for local cuisine.",
        "facilities": [
            ("Riverside outdoor pool", "pool", 1),
            ("Multiple restaurants + bar", "dining", 3),
            ("Full-service spa & hammam", "spa", 1),
            ("Fitness centre", "sport", 1),
            ("Business centre", "business", 1),
        ],
    },
    "the savoy": {
        "description": "A landmark hotel in the heart of Sharm El Sheikh, The Savoy is known for its elegant rooms, mature gardens, and prime position close to Naama Bay.",
        "neighborhood": "5 minutes from Naama Bay and 15 minutes from the airport.",
        "house_rules": "Check-in from 14:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "The gardens are wonderful for an evening stroll.\nBook a sea-view room for the best experience.",
        "facilities": [
            ("Two outdoor pools", "pool", 2),
            ("Private beach", "beach", 1),
            ("Multiple restaurants + bars", "dining", 4),
            ("Spa & fitness centre", "spa", 1),
            ("Tennis courts", "sport", 2),
            ("Kids' club", "family", 1),
        ],
    },
    "hilton taba": {
        "description": "Perched on the Gulf of Aqaba coast at Taba, Hilton Taba Resort & Nelson Village offers a peaceful escape with dramatic views of the sea and the Sinai mountains.",
        "neighborhood": "On the Gulf of Aqaba coast at Taba, close to the Israeli border.",
        "house_rules": "Check-in from 14:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "The dive sites in the Gulf of Aqaba are spectacular.\nAsk for a sea-view room for the sunrise.",
        "facilities": [
            ("Private beach", "beach", 1),
            ("Multiple outdoor pools", "pool", 3),
            ("Dive centre & water sports", "sport", 2),
            ("Multiple restaurants + bars", "dining", 4),
            ("Spa & fitness centre", "spa", 1),
            ("Kids' club", "family", 1),
        ],
    },
    "hilton nuweiba": {
        "description": "Set on a quiet stretch of Gulf of Aqaba coastline, Hilton Nuweiba Resort offers a tranquil escape from the busier resorts of the Sinai.",
        "neighborhood": "On the Gulf of Aqaba coast at Nuweiba, about 90 minutes from Sharm El Sheikh airport.",
        "house_rules": "Check-in from 14:00, check-out by 12:00.\nNo smoking inside guest rooms.\nChildren welcome.",
        "cancellation": "Free cancellation up to 48 hours before check-in.",
        "check_in_details": "Valid passport required. Card pre-authorisation on arrival.",
        "tips": "The house reef is superb — bring an underwater camera.\nBook a sea-view room for the sunrise.",
        "facilities": [
            ("Private beach with house reef", "beach", 1),
            ("Outdoor pool", "pool", 2),
            ("Dive centre", "sport", 1),
            ("Restaurant + beach bar", "dining", 2),
            ("Spa treatments", "spa", 1),
            ("Kids' club", "family", 1),
        ],
    },

# ══════════════════════════════════════════════════════════════════
#  TEMPLATE CONTENT — for hotels not in CURATED
# ══════════════════════════════════════════════════════════════════

}  # end CURATED

FACILITIES_BY_STARS = {
    5: [
        ("Outdoor swimming pool", "pool", 2),
        ("Full-service spa & wellness centre", "spa", 1),
        ("Multiple restaurants & bars", "dining", 3),
        ("Fitness centre", "sport", 1),
        ("24-hour reception & concierge", "service", 1),
        ("Free high-speed Wi-Fi", "connectivity", 1),
    ],
    4: [
        ("Outdoor swimming pool", "pool", 1),
        ("Restaurant & bar", "dining", 2),
        ("Fitness centre", "sport", 1),
        ("Free Wi-Fi in public areas", "connectivity", 1),
    ],
    3: [
        ("Outdoor swimming pool", "pool", 1),
        ("Restaurant", "dining", 1),
        ("Free Wi-Fi in lobby", "connectivity", 1),
    ],
}

INCLUSIONS_TEMPLATE = {
    "beach": [
        "Daily breakfast (buffet)",
        "Use of outdoor swimming pool",
        "Access to private beach",
        "Free Wi-Fi in public areas",
        "All taxes and service charges",
    ],
    "city": [
        "Daily breakfast (buffet)",
        "Free Wi-Fi in public areas",
        "24-hour reception",
        "Concierge service",
        "All taxes and service charges",
    ],
    "nile": [
        "Daily breakfast (buffet)",
        "Use of outdoor swimming pool",
        "Wi-Fi in public areas",
        "Shuttle to nearby sites",
        "All taxes and service charges",
    ],
}

EXCLUSIONS_TEMPLATE = [
    "Flights (unless stated in the package)",
    "Airport transfers (can be arranged)",
    "Personal expenses and souvenirs",
    "Tips and gratuities",
    "Travel insurance",
]

DESTINATION_FAQS = {
    "luxor": [
        ("How far is the Valley of the Kings?",
         "The Valley of the Kings is on the West Bank, about 30-40 minutes from the hotel by road plus ferry. Most hotels can arrange guided tours."),
        ("What's the best time to visit the temples?",
         "Early morning (6-9am) and late afternoon (4-6pm) are cooler and quieter. Avoid midday heat in summer."),
        ("Is a hot-air balloon ride worth it?",
         "Yes — dawn balloon flights over the Theban Necropolis are a highlight. Book at least a day in advance."),
    ],
    "sharm": [
        ("Is Ras Mohammed National Park accessible?",
         "Yes — about 40 minutes by road. Most hotels arrange snorkelling and diving day trips to Ras Mohammed."),
        ("Can I snorkel from the hotel beach?",
         "Most resorts on the Sinai coast have house reefs accessible from the beach. Bring reef-safe sunscreen."),
        ("What's the best time to visit Naama Bay?",
         "Early evening is best — the promenade comes alive with restaurants, cafés, and street performers."),
    ],
    "hurghada": [
        ("Is Giftun Island worth a day trip?",
         "Yes — Giftun Island offers some of the best snorkelling in the northern Red Sea. Most hotels arrange day trips."),
        ("Can I dive in Hurghada?",
         "Yes — the Red Sea around Hurghada has excellent dive sites. Most hotels have PADI dive centres on-site."),
        ("What's the best time to visit the marina?",
         "Evening — the marina comes alive with yachts, restaurants, and cafés. It's a 10-15 minute taxi ride from most hotels."),
    ],
    "cairo": [
        ("How far are the Pyramids of Giza?",
         "About 45-60 minutes from central Cairo by car, depending on traffic. Most hotels arrange guided tours."),
        ("What's the best way to visit Khan el-Khalili?",
         "Use a hotel-arranged taxi or guide — the bazaar is easy to get lost in, and having a local guide makes the experience better."),
        ("Is the Egyptian Museum worth visiting?",
         "Absolutely — the museum's collection of ancient Egyptian artefacts is world-class, including the Tutankhamun treasures."),
    ],
    "dahab": [
        ("Is the Blue Hole nearby?",
         "Yes — about 20 minutes by car or bicycle up the coast. The Blue Hole is one of the world's most famous dive sites."),
        ("Can I snorkel from the shore?",
         "Yes — Dahab's shoreline has excellent snorkelling. The house reefs are accessible directly from the beach."),
        ("What's the best way to get around Dahab?",
         "Dahab is small — most places are within walking distance. Bicycles can be rented for longer trips."),
    ],
}

DESTINATION_TIPS = {
    "luxor": [
        "Early-morning excursions to the temples avoid the midday heat.",
        "Bring a light scarf — useful both for sun protection and visiting mosques.",
        "Book hot-air balloon rides at dawn — the views over the Theban hills are unforgettable.",
        "Carry small change for tips (baksheesh) — it's expected for good service.",
        "Dress modestly when visiting religious sites — shoulders and knees covered.",
    ],
    "sharm": [
        "Bring reef-safe sunscreen — it protects the Red Sea coral.",
        "Book snorkelling or diving trips early — the best slots fill up fast.",
        "Evenings in Sharm are warm — light layers are enough.",
        "Naama Bay is best explored on foot — the promenade is a highlight.",
        "Carry cash for the Old Market — not all stalls accept cards.",
    ],
    "hurghada": [
        "Book a Giftun Island boat trip early — the best departures sell out.",
        "Bring reef-safe sunscreen — it protects the Red Sea coral.",
        "Try the Egyptian breakfast — ful medames and fresh flatbread.",
        "The marina is a great evening destination — shops, restaurants, and cafés.",
        "Snorkelling is best in the morning when the water is calmest.",
    ],
    "cairo": [
        "Allow extra time for traffic — Cairo's roads are busy at all hours.",
        "Visit the Pyramids at dawn or late afternoon to avoid crowds.",
        "Dress modestly when visiting religious sites — shoulders and knees covered.",
        "Carry small change for tips (baksheesh) — it's expected for good service.",
        "Bring a hat and water — the sun is strong year-round.",
    ],
    "dahab": [
        "Bring reef-safe sunscreen — it protects the Red Sea coral.",
        "Rent a bicycle to explore the coast — the road to the Blue Hole is beautiful.",
        "Evenings in Dahab are cooler than Sharm — pack a light jumper.",
        "The promenade's cafés are excellent for cheap, delicious meals.",
        "Book dives a week ahead in high season.",
    ],
}

DESTINATION_NEIGHBORHOOD = {
    "luxor": "Central Luxor, walking distance to the Nile, Luxor Temple, and the Luxor Museum. Karnak Temple is a short taxi ride north.",
    "sharm": "In the Sharm El Sheikh area, with easy access to Naama Bay's promenade, restaurants, and beaches.",
    "hurghada": "On the Red Sea coast, close to Hurghada's marina, Sheraton Road shopping, and the town's dive operators.",
    "cairo": "In central Cairo, walking distance to the Nile and close to Tahrir Square, the Egyptian Museum, and Khan el-Khalili.",
    "dahab": "On Dahab's coast, a short walk from the main promenade with its cafés, dive shops, and craft stalls.",
    "taba": "On the Gulf of Aqaba coast at Taba, with dramatic desert mountains on one side and calm blue waters on the other.",
    "nuweiba": "On the Gulf of Aqaba coast, offering quiet beaches and easy access to some of the Sinai's best reefs.",
    "marsa": "On the Red Sea coast at Marsa Alam, close to superb dive sites and the region's quiet beaches.",
    "el gouna": "In El Gouna, a purpose-built resort town with its own marina, lagoons, and golf course.",
    "soma bay": "In Soma Bay, a secluded peninsula with a championship golf course and one of the best house reefs on the Red Sea.",
    "makadi": "In Makadi Bay, a sheltered bay ideal for swimming, snorkelling, and beginner dives.",
    "tiran": "Near Tiran Island, with direct access to some of the finest reefs in the northern Red Sea.",
}

FAQ_TEMPLATE_FALLBACK = [
    ("What time is check-in / check-out?",
     "Check-in is from 14:00, check-out by 12:00. Early check-in and late check-out may be available on request, subject to availability."),
    ("Is Wi-Fi included?",
     "Yes, complimentary Wi-Fi is available in public areas and most guest rooms."),
    ("Do you offer airport transfers?",
     "Yes, we can arrange airport transfers for an additional fee. Please contact the hotel in advance with your flight details."),
]

TIP_TEMPLATE_FALLBACK = [
    "Bring reef-safe sunscreen — it protects the coral reefs.",
    "Book snorkelling or diving trips early — the best slots fill up fast.",
    "Carry small change for tips (baksheesh) — it's expected for good service.",
]# ══════════════════════════════════════════════════════════════════
#  Helper functions
# ══════════════════════════════════════════════════════════════════
def _dest_key(name: str) -> str:
    """Return the destination key that matches the destination name."""
    n = (name or "").strip().lower()
    for key in DEST_COORDS:
        if key in n:
            return key
    return "hurghada"


def _coords_for(dest_name: str) -> tuple[float, float]:
    key = _dest_key(dest_name)
    return DEST_COORDS.get(key, DEST_COORDS["hurghada"])


def _maps_url(hotel_name: str, coords: tuple[float, float]) -> str:
    lat, lng = coords
    q = hotel_name.replace(" ", "+")
    return f"https://www.google.com/maps/search/?api=1&query={q}&center={lat},{lng}"


def _hotel_type_from_name(name: str) -> str:
    """Return 'nile' | 'city' | 'beach' — used for inclusions/tips templates."""
    n = (name or "").lower()
    if "nile" in n or "cruise" in n:
        return "nile"
    if any(k in n for k in ("cairo", "fairmont", "marriott cairo", "pyramisa cairo")):
        return "city"
    return "beach"


def _find_curated(name: str) -> dict | None:
    """Return the CURATED entry whose key appears in the hotel name."""
    n = (name or "").strip().lower()
    # Longest keys first so 'hilton luxor' beats 'hilton'
    for key in sorted(CURATED, key=len, reverse=True):
        if key in n:
            return CURATED[key]
    return None


def _template_description(name: str, stars: int, dest_key: str) -> str:
    """Generate a rich template description based on stars + destination."""
    star_word = {5: "5-star", 4: "4-star", 3: "3-star"}.get(stars, "well-appointed")
    dest_nice = dest_key.replace("_", " ").title()

    star_intro = {
        5: (
            f"{name} is a {star_word} property in {dest_nice}, offering "
            f"elegant rooms, attentive service, and a full range of "
            f"facilities for both leisure and business travellers. Guests "
            f"can expect a spa, multiple restaurants, and a pool with "
            f"comfortable sun terraces."
        ),
        4: (
            f"{name} is a {star_word} property in {dest_nice}, offering "
            f"comfortable rooms, a restaurant and bar, an outdoor pool, and "
            f"easy access to the area's main attractions."
        ),
        3: (
            f"{name} is a {star_word} property in {dest_nice}, offering "
            f"clean, comfortable rooms, an outdoor pool, and a restaurant "
            f"serving local and international cuisine."
        ),
    }.get(stars, f"{name} is a well-appointed property in {dest_nice}.")

    dest_addendum = {
        "luxor": "The temples, museums, and Nile cruises that make Luxor famous are all within easy reach.",
        "sharm": "The reefs, beaches, and promenades of Sharm El Sheikh are within easy reach.",
        "hurghada": "The marina, dive sites, and Red Sea beaches of Hurghada are within easy reach.",
        "cairo": "The Egyptian Museum, Khan el-Khalili, and the Pyramids of Giza are all within reach.",
        "dahab": "The famous dive sites and bohemian promenade of Dahab are within easy reach.",
    }.get(dest_key, f"The main attractions of {dest_nice} are within easy reach.")

    return (
        f"{star_intro} {dest_addendum} "
        f"[Sample content — verify before publishing.]"
    )


def _clear_children(hotel: Hotel, dry_run: bool) -> None:
    """Delete existing facilities / inclusions / exclusions / FAQs / tips."""
    if dry_run:
        return
    for Model in (HotelFacility, HotelInclusion, HotelExclusion, HotelFAQ, HotelTip):
        db.session.query(Model).filter_by(hotel_id=hotel.id).delete()


def _apply_curated(hotel: Hotel, curated: dict, dry_run: bool) -> None:
    """Write curated content to a hotel + its child tables."""
    if dry_run:
        return

    # Core fields
    hotel.description = curated.get("description")
    hotel.neighborhood_info = curated.get("neighborhood")
    hotel.useful_tips = curated.get("tips")
    hotel.house_rules = curated.get("house_rules")
    hotel.cancellation_policy = curated.get("cancellation")
    hotel.check_in_details = curated.get("check_in_details")
    hotel.check_in_time = hotel.check_in_time or "14:00"
    hotel.check_out_time = hotel.check_out_time or "12:00"

    # Facilities
    for name, ftype, qty in curated.get("facilities", []):
        db.session.add(HotelFacility(
            hotel_id=hotel.id,
            name=name,
            type=_safe_facility_type(ftype),
            quantity=qty,
        ))

    # Inclusions / exclusions
    hotel_type = _hotel_type_from_name(hotel.name)
    for i, item in enumerate(
        INCLUSIONS_TEMPLATE.get(hotel_type, INCLUSIONS_TEMPLATE["beach"]),
        start=1,
    ):
        db.session.add(HotelInclusion(hotel_id=hotel.id, item=item, sort_order=i))
    for i, item in enumerate(EXCLUSIONS_TEMPLATE, start=1):
        db.session.add(HotelExclusion(hotel_id=hotel.id, item=item, sort_order=i))

    # FAQs — use destination-specific where available
    dest_key = _dest_key(hotel.name + " " + (hotel.address or ""))
    faqs = DESTINATION_FAQS.get(dest_key, FAQ_TEMPLATE_FALLBACK)
    for i, (q, a) in enumerate(faqs, start=1):
        db.session.add(HotelFAQ(hotel_id=hotel.id, question=q, answer=a, sort_order=i))

    # Tips — destination-specific
    tips = DESTINATION_TIPS.get(dest_key, TIP_TEMPLATE_FALLBACK)
    for i, tip in enumerate(tips, start=1):
        db.session.add(HotelTip(hotel_id=hotel.id, tip=tip, sort_order=i))


def _apply_template(hotel: Hotel, dest_name: str, dry_run: bool) -> None:
    """Write template content (destination + stars aware) to a hotel."""
    if dry_run:
        return

    stars = hotel.stars or 3
    dest_key = _dest_key(dest_name)

    # Core fields
    hotel.description = _template_description(hotel.name, stars, dest_key)
    hotel.neighborhood_info = DESTINATION_NEIGHBORHOOD.get(
        dest_key,
        f"{hotel.name} is located in {dest_name}. "
        f"[Sample content — verify before publishing.]",
    )
    hotel.useful_tips = "\n".join(
        DESTINATION_TIPS.get(dest_key, TIP_TEMPLATE_FALLBACK)[:3]
    )
    hotel.check_in_time = hotel.check_in_time or "14:00"
    hotel.check_out_time = hotel.check_out_time or "12:00"
    hotel.check_in_details = (
        "Valid passport or ID required at check-in. A credit card "
        "pre-authorisation may be requested for incidentals. "
        "[Sample content — verify before publishing.]"
    )
    hotel.house_rules = (
        "No smoking inside guest rooms.\n"
        "Pets are not permitted.\n"
        "Quiet hours from 23:00 to 07:00.\n"
        "Children are welcome."
    )
    hotel.cancellation_policy = (
        "Standard cancellation policy applies. Please check the rate "
        "conditions at the time of booking. "
        "[Sample content — verify before publishing.]"
    )

    # Facilities — by star rating
    for name, ftype, qty in FACILITIES_BY_STARS.get(stars, FACILITIES_BY_STARS[3]):
        db.session.add(HotelFacility(
            hotel_id=hotel.id,
            name=name,
            type=_safe_facility_type(ftype),
            quantity=qty,
        ))

    # Inclusions / exclusions
    hotel_type = _hotel_type_from_name(hotel.name)
    for i, item in enumerate(
        INCLUSIONS_TEMPLATE.get(hotel_type, INCLUSIONS_TEMPLATE["beach"]),
        start=1,
    ):
        db.session.add(HotelInclusion(hotel_id=hotel.id, item=item, sort_order=i))
    for i, item in enumerate(EXCLUSIONS_TEMPLATE, start=1):
        db.session.add(HotelExclusion(hotel_id=hotel.id, item=item, sort_order=i))

    # FAQs — destination-specific
    faqs = DESTINATION_FAQS.get(dest_key, FAQ_TEMPLATE_FALLBACK)
    for i, (q, a) in enumerate(faqs, start=1):
        db.session.add(HotelFAQ(hotel_id=hotel.id, question=q, answer=a, sort_order=i))

    # Tips — destination-specific
    tips = DESTINATION_TIPS.get(dest_key, TIP_TEMPLATE_FALLBACK)
    for i, tip in enumerate(tips, start=1):
        db.session.add(HotelTip(hotel_id=hotel.id, tip=tip, sort_order=i))


# ══════════════════════════════════════════════════════════════════
#  Main entry point
# ══════════════════════════════════════════════════════════════════
def enrich(dry_run: bool, only_curated: bool) -> int:
    app = create_app()
    with app.app_context():
        hotels = db.session.query(Hotel).order_by(Hotel.id).all()
        destinations = {d.id: d.name for d in db.session.query(Destination).all()}

        n_curated = 0
        n_template = 0
        n_skipped = 0
        n_curated_misses: list[str] = []

        for h in hotels:
            dest_name = destinations.get(h.destination_id, "Egypt")
            curated = _find_curated(h.name)

            if only_curated and not curated:
                n_skipped += 1
                continue

            # Coordinates + Maps URL
            coords = _coords_for(dest_name)
            if not dry_run:
                if h.latitude is None:
                    h.latitude = Decimal(str(coords[0]))
                if h.longitude is None:
                    h.longitude = Decimal(str(coords[1]))
                if not h.google_maps_url:
                    h.google_maps_url = _maps_url(h.name, coords)

            # Clear existing children (idempotent re-runs)
            _clear_children(h, dry_run)

            if curated:
                _apply_curated(h, curated, dry_run)
                n_curated += 1
                tag = "CURATED "
            else:
                _apply_template(h, dest_name, dry_run)
                n_template += 1
                tag = "template"
                # Track potential misses (chains that should be curated)
                name_lower = (h.name or "").lower()
                for brand in (
                    "hilton", "movenpick", "sheraton", "sonesta",
                    "marriott", "fairmont", "kempinski", "radisson",
                    "ritz", "four seasons", "rixos", "steigenberger",
                    "sofitel", "hyatt",
                ):
                    if brand in name_lower:
                        n_curated_misses.append(h.name)
                        break

            print(f"  [{tag}] {h.id:4d} | {h.name[:60]}")

        if not dry_run:
            db.session.commit()
            print("\n=== COMMITTED ===")
        else:
            print("\n=== DRY RUN (nothing committed) ===")

        print(f"Curated hotels enriched:   {n_curated}")
        print(f"Templated hotels enriched: {n_template}")
        if only_curated:
            print(f"Skipped (not curated):     {n_skipped}")
        if n_curated_misses:
            print("\n⚠  Potential curated misses (brands without an entry):")
            for name in n_curated_misses:
                print(f"     {name}")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Show the plan without committing changes.")
    ap.add_argument("--only-curated", action="store_true",
                    help="Only enrich hotels that have curated content.")
    args = ap.parse_args()
    return enrich(dry_run=args.dry_run, only_curated=args.only_curated)


if __name__ == "__main__":
    raise SystemExit(main())
