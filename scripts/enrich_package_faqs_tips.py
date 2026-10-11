"""
scripts/enrich_package_faqs_tips.py
────────────────────────────────────
Populate PackageFAQ and PackageTip rows for every package.

Content is destination + package-type aware:
  - Nile Cruise  → cruise FAQs (dress code, motion, meals on board)
  - Hurghada     → Red Sea + Giftun Island + dive FAQs
  - Sharm        → Naama Bay + Ras Mohammed FAQs
  - Luxor        → temples + Valley of the Kings FAQs
  - Cairo        → pyramids + museum FAQs

Idempotent: packages that already have any FAQ or Tip are skipped.
Re-run safe. Use --force to overwrite.

USAGE
    python scripts/enrich_package_faqs_tips.py --dry-run
    python scripts/enrich_package_faqs_tips.py
    python scripts/enrich_package_faqs_tips.py --force
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import (  # noqa: E402
    Package,
    PackageFAQ,
    PackageTip,
    Destination,
    Hotel,
)


# ══════════════════════════════════════════════════════════════════
#  FAQ libraries
# ══════════════════════════════════════════════════════════════════
GENERIC_FAQS: list[tuple[str, str]] = [
    (
        "What's included in the package price?",
        "Your package covers return flights, airport and hotel transfers, "
        "accommodation for the duration of your stay, and everything listed in "
        "the 'What's included' section. Personal expenses, tips, and optional "
        "excursions are not included unless specified.",
    ),
    (
        "Can I book the package for a specific departure date?",
        "Yes — our system shows live availability by date. Pick your preferred "
        "dates on the search page and choose from the available windows. If you "
        "need a custom date outside the standard calendar, request a quote and "
        "our team will arrange it.",
    ),
    (
        "Is travel insurance required?",
        "We strongly recommend comprehensive travel insurance covering medical "
        "care, cancellations, and personal belongings. It is not included in the "
        "package price and must be arranged independently.",
    ),
    (
        "How do I get my booking confirmation?",
        "You will receive an instant confirmation email with your booking "
        "reference, flight details, hotel information, and full itinerary. If "
        "it doesn't arrive within 15 minutes, check your spam folder or contact "
        "us directly.",
    ),
    (
        "What's the cancellation policy?",
        "Standard packages offer free cancellation up to 30 days before "
        "departure. Cancellations within 30 days may be charged a percentage of "
        "the total. Peak dates (Christmas, New Year, Easter) may have stricter "
        "terms — the exact policy is shown at booking.",
    ),
    (
        "Can I book for a group?",
        "Absolutely — we handle groups from 2 to 30+ travellers. Group bookings "
        "may qualify for discounted rates, free place for a group leader, and "
        "custom private excursions. Contact us with your numbers for a tailored "
        "quote.",
    ),
    (
        "Are flights from my local airport available?",
        "We work with multiple UK origin airports (London Gatwick, Luton, "
        "Manchester, Glasgow, Birmingham, Bristol, Leeds Bradford, and Heathrow). "
        "Flights are selectable on the package detail page with their prices "
        "shown separately.",
    ),
    (
        "Do I need a visa for Egypt?",
        "Most UK, EU, US, and Canadian passport holders can obtain a visa on "
        "arrival or online via the Egyptian e-Visa portal. Check your specific "
        "nationality's requirements before travel. The visa fee is not included "
        "in the package unless stated otherwise.",
    ),
]

NILE_FAQS: list[tuple[str, str]] = [
    (
        "What is the cabin like on the cruise ship?",
        "Cabins are modern and en-suite, with air conditioning, a picture "
        "window or balcony, and storage. Nile cruise ships typically offer "
        "3-5* categories; your package specifies the ship's standard.",
    ),
    (
        "Are all meals included on the cruise?",
        "Yes — full board (breakfast, lunch, and dinner) is included throughout "
        "the cruise. Alcoholic drinks and premium beverages are charged extra.",
    ),
    (
        "Do I need to bring anything for the temples?",
        "Comfortable walking shoes, a hat, sunscreen, and a light scarf to cover "
        "shoulders and knees at religious sites. Bring cash for tips (baksheesh) "
        "and any souvenirs.",
    ),
    (
        "What's the dress code on board?",
        "Smart-casual in the evenings. Swimwear by the pool, but not in the "
        "restaurant. A light jacket is useful for early morning excursions.",
    ),
    (
        "Is the cruise suitable for children?",
        "Yes — many Nile cruises welcome families, though the pace and temple "
        "visits may be long for very young children. Discounted child rates and "
        "family cabins are available on request.",
    ),
]

HURGHADA_FAQS: list[tuple[str, str]] = [
    (
        "Can I add diving or snorkelling trips?",
        "Yes — Giftun Island day trips, intro dives, and full PADI courses can "
        "be added to your package. Prices vary by trip length and equipment "
        "included. Ask us for a quote or book through the hotel dive centre.",
    ),
    (
        "Is the Red Sea warm enough to swim all year?",
        "Yes — the Red Sea is swimmable year-round, with temperatures ranging "
        "from around 22°C in winter to 30°C in summer. A light wetsuit is "
        "recommended for longer snorkelling trips in winter.",
    ),
    (
        "Is Hurghada good for families?",
        "Very — most resorts are family-friendly with kids' clubs, shallow "
        "pools, and waterslides. Boat trips and submarine excursions are "
        "popular with children aged 5+.",
    ),
    (
        "What's the best time to visit Hurghada?",
        "October through April offers the most comfortable temperatures for "
        "land excursions. Summer (June–August) is hot but perfect for water "
        "activities and diving.",
    ),
]

SHARM_FAQS: list[tuple[str, str]] = [
    (
        "Can we visit Ras Mohammed National Park?",
        "Yes — most Sharm packages can include a day trip to Ras Mohammed "
        "National Park for snorkelling or diving at one of the world's finest "
        "marine parks. Ask us about availability and pricing.",
    ),
    (
        "What's the best area to stay in Sharm?",
        "Naama Bay suits travellers who want nightlife and central access; "
        "Ras Um Sid offers quieter resorts with excellent shore diving; "
        "Sharks Bay is popular for its house reef and family-friendly resorts.",
    ),
    (
        "Is Sharm El Sheikh safe?",
        "Yes — the Sharm El Sheikh area is one of Egypt's most heavily "
        "protected tourist zones, with visible security around resorts and the "
        "airport. Travellers should follow standard precautions and respect "
        "local customs.",
    ),
    (
        "Can we combine Sharm with a Nile cruise or Luxor trip?",
        "Yes — internal flights between Sharm, Luxor, and Cairo make it easy to "
        "build a multi-centre itinerary. Ask us for a combined quote.",
    ),
]

LUXOR_FAQS: list[tuple[str, str]] = [
    (
        "What should I wear for the temples?",
        "Comfortable, breathable clothing with shoulders and knees covered. "
        "A hat, sunglasses, and a light scarf are useful year-round. Closed-toe "
        "shoes are best for the uneven grounds of the tombs and temples.",
    ),
    (
        "Is the Valley of the Kings very hot?",
        "Yes — the West Bank can reach 40°C+ in summer. Visit early morning "
        "(6–9am) or late afternoon to avoid the worst heat. All tombs are "
        "underground but the walk between them is fully exposed.",
    ),
    (
        "Do I need a guide in Luxor?",
        "We highly recommend a certified Egyptologist guide — the depth of "
        "context they bring to the temples and tombs is unmatched. Guides can "
        "be added to any Luxor package.",
    ),
    (
        "Can we do a hot-air balloon ride over Luxor?",
        "Yes — dawn balloon flights over the Theban Necropolis are a highlight. "
        "They can be added to your package for an additional fee and are best "
        "booked well in advance.",
    ),
]

CAIRO_FAQS: list[tuple[str, str]] = [
    (
        "How far are the Pyramids of Giza from the hotel?",
        "About 45-60 minutes from central Cairo by car, depending on traffic. "
        "Guided tours to the Pyramids, Sphinx, Sakkara, and Memphis are "
        "available as add-ons.",
    ),
    (
        "Is the Grand Egyptian Museum worth visiting?",
        "Absolutely — the GEM is one of the world's greatest museums, "
        "displaying the complete Tutankhamun collection and thousands of "
        "artefacts spanning 7,000 years of Egyptian history.",
    ),
    (
        "Can we do a Nile dinner cruise in Cairo?",
        "Yes — evening Nile dinner cruises with live music and entertainment "
        "are a popular addition. They typically run 2 hours and include a "
        "buffet dinner.",
    ),
]


# ══════════════════════════════════════════════════════════════════
#  Tips libraries
# ══════════════════════════════════════════════════════════════════
GENERIC_TIPS: list[str] = [
    "Book excursions early — the best guides and time slots fill up months in advance.",
    "Carry small denominations of Egyptian pounds for tips (baksheesh) — it is expected for good service.",
    "Pack light layers — temperatures can swing 15°C between day and night, especially in winter.",
    "Bring a universal adaptor — Egypt uses European-style two-pin plugs (Type C/F).",
    "Keep a copy of your passport and travel insurance in a separate bag.",
]

NILE_TIPS: list[str] = [
    "Bring a light jacket for early-morning temple excursions — the deck breeze can be cool.",
    "Motion sickness tablets are useful if you're sensitive — the Nile is calm but not always still.",
    "Tipping on Nile cruises is standard — typically £5-10 per person per day, pooled at the end.",
    "Book the upper-deck cabins for the best views — the difference in price is worth it.",
    "Bring a book or two — some sailing hours between temples are wonderfully slow.",
]

HURGHADA_TIPS: list[str] = [
    "Use reef-safe sunscreen only — regular sunscreen harms the Red Sea coral.",
    "Book a Giftun Island boat trip early — the best departures sell out fast.",
    "Snorkelling is best in the morning when the water is calmest and visibility is highest.",
    "Bring a waterproof phone pouch — sea spray gets everywhere on boat trips.",
    "Evenings can be breezy on the marina — a light cardigan is useful year-round.",
]

SHARM_TIPS: list[str] = [
    "Use reef-safe sunscreen — it protects the Red Sea coral you came to see.",
    "Naama Bay is best explored on foot in the early evening when the promenade comes alive.",
    "Book a Ras Mohammed day trip at least a week ahead in high season.",
    "Evenings in Sharm are warm — light layers are enough.",
    "The Old Market is great for authentic souvenirs — bargain politely.",
]

LUXOR_TIPS: list[str] = [
    "Start early — the Valley of the Kings is cooler and quieter before 9am.",
    "Hire a certified Egyptologist guide — the difference in understanding is enormous.",
    "Bring tissues — public restrooms at the sites often run out of paper.",
    "Learn a few Arabic greetings — 'shukran' (thank you) goes a long way.",
    "Wear a hat and sunglasses — the sun is intense even in winter.",
]

CAIRO_TIPS: list[str] = [
    "Allow extra time for traffic — Cairo's roads are busy at all hours.",
    "Visit the Pyramids at dawn or late afternoon to avoid crowds and midday heat.",
    "Dress modestly when visiting religious sites — shoulders and knees covered.",
    "Carry small change for tips — baksheesh is expected for good service.",
    "Bring a hat and water — the sun is strong year-round.",
]


# ══════════════════════════════════════════════════════════════════
#  Bucketing — pick content based on destination + hotel name
# ══════════════════════════════════════════════════════════════════
def _bucket(package: Package, dest_name: str, hotel_name: str) -> str:
    text = f"{dest_name} {hotel_name} {package.name or ''}".lower()
    if "nile" in text or "cruise" in text:
        return "nile"
    if "hurghada" in text:
        return "hurghada"
    if "sharm" in text or "naama" in text or "ras um sid" in text:
        return "sharm"
    if "luxor" in text:
        return "luxor"
    if "cairo" in text or "giza" in text or "pyramid" in text:
        return "cairo"
    return "generic"


BUCKET_FAQS = {
    "nile":     NILE_FAQS,
    "hurghada": HURGHADA_FAQS,
    "sharm":    SHARM_FAQS,
    "luxor":    LUXOR_FAQS,
    "cairo":    CAIRO_FAQS,
    "generic":  [],
}

BUCKET_TIPS = {
    "nile":     NILE_TIPS,
    "hurghada": HURGHADA_TIPS,
    "sharm":    SHARM_TIPS,
    "luxor":    LUXOR_TIPS,
    "cairo":    CAIRO_TIPS,
    "generic":  [],
}


# ══════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════
def enrich(dry_run: bool, force: bool) -> int:
    app = create_app()
    with app.app_context():
        packages = db.session.query(Package).order_by(Package.id).all()
        destinations = {d.id: d.name for d in db.session.query(Destination).all()}
        hotels = {h.id: h.name for h in db.session.query(Hotel).all()}

        n_faqs_added = 0
        n_tips_added = 0
        n_skipped = 0

        for p in packages:
            # Idempotency: skip if this package already has content
            if not force:
                existing_faqs = (
                    db.session.query(PackageFAQ)
                    .filter_by(package_id=p.id)
                    .count()
                )
                existing_tips = (
                    db.session.query(PackageTip)
                    .filter_by(package_id=p.id)
                    .count()
                )
                if existing_faqs > 0 or existing_tips > 0:
                    n_skipped += 1
                    continue

            dest_name = destinations.get(p.destination_id, "")
            hotel_name = hotels.get(p.hotel_id, "")
            bucket = _bucket(p, dest_name, hotel_name)

            # ─── FAQs ───
            faqs_to_add = list(BUCKET_FAQS.get(bucket, [])) + list(GENERIC_FAQS)
            seen_q: set[str] = set()
            unique_faqs: list[tuple[str, str]] = []
            for q, a in faqs_to_add:
                if q in seen_q:
                    continue
                seen_q.add(q)
                unique_faqs.append((q, a))
            unique_faqs = unique_faqs[:5]

            if not dry_run:
                for i, (q, a) in enumerate(unique_faqs, start=1):
                    db.session.add(PackageFAQ(
                        package_id=p.id,
                        question=q,
                        answer=a,
                        sort_order=i,
                    ))
                    n_faqs_added += 1
            else:
                n_faqs_added += len(unique_faqs)

            # ─── Tips ───
            tips_to_add = list(BUCKET_TIPS.get(bucket, [])) + list(GENERIC_TIPS)
            seen_t: set[str] = set()
            unique_tips: list[str] = []
            for t in tips_to_add:
                if t in seen_t:
                    continue
                seen_t.add(t)
                unique_tips.append(t)
            unique_tips = unique_tips[:4]

            if not dry_run:
                for i, tip in enumerate(unique_tips, start=1):
                    db.session.add(PackageTip(
                        package_id=p.id,
                        tip=tip,
                        sort_order=i,
                    ))
                    n_tips_added += 1
            else:
                n_tips_added += len(unique_tips)

            print(f"  [{bucket:9s}] {p.id:4d} | {p.name[:55]:55s} | "
                  f"FAQs: {len(unique_faqs)} | Tips: {len(unique_tips)}")

        if not dry_run:
            db.session.commit()
            print("\n=== COMMITTED ===")
        else:
            print("\n=== DRY RUN (nothing committed) ===")

        print(f"FAQs added:   {n_faqs_added}")
        print(f"Tips added:   {n_tips_added}")
        print(f"Skipped:      {n_skipped} (already had content)")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite existing FAQs/Tips")
    args = ap.parse_args()
    return enrich(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())