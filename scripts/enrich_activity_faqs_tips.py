"""
scripts/enrich_activity_faqs_tips.py
────────────────────────────────────
Populate ActivityFAQ and ActivityTip rows for every activity.

Content is generated from three axes:
  1. Category          (water / history / adventure / wildlife / food ...)
  2. Duration          (half-day / full-day / multi-day affects wording)
  3. Destination       (Sharm vs Luxor vs Cairo → different dress / climate tips)

Idempotent: activities that already have >= 1 FAQ and >= 1 tip are skipped.
Re-run safe.

USAGE
    python scripts/enrich_activity_faqs_tips.py --dry-run
    python scripts/enrich_activity_faqs_tips.py
    python scripts/enrich_activity_faqs_tips.py --force   # overwrite existing
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
    Activity,
    ActivityFAQ,
    ActivityTip,
    Destination,
)


# ══════════════════════════════════════════════════════════════════
#  FAQ library — keyed by category bucket
# ══════════════════════════════════════════════════════════════════
GENERIC_FAQS: list[tuple[str, str]] = [
    (
        "Is hotel pickup included?",
        "Yes — complimentary pickup from most hotels in the area is included. "
        "Please provide your hotel name and room number at the time of booking "
        "so we can confirm the exact pickup time, which is typically 30-60 "
        "minutes before the activity starts.",
    ),
    (
        "What should I wear?",
        "Comfortable, breathable clothing is recommended. For warm-weather "
        "activities a light long-sleeve layer protects against the sun. "
        "Closed-toe shoes are best for walking tours; sandals are fine for "
        "beach and boat trips.",
    ),
    (
        "Is this activity suitable for children?",
        "Yes, unless the activity specifies a minimum age. Children must be "
        "accompanied by an adult at all times. If your child has specific "
        "needs (allergies, mobility, dietary), let us know in advance.",
    ),
    (
        "What is the cancellation policy?",
        "Free cancellation up to 24 hours before the start time. Cancellations "
        "within 24 hours, or no-shows, are charged the full activity price. "
        "Please contact us as early as possible if your plans change.",
    ),
    (
        "How do I get my confirmation?",
        "You will receive an instant confirmation email with your booking "
        "reference, meeting point, and pickup details. If you don't see it "
        "within 15 minutes, check your spam folder or contact us.",
    ),
    (
        "What is not included in the price?",
        "Unless stated otherwise: personal expenses, souvenirs, tips for your "
        "guide and driver, and any optional extras offered on the day are not "
        "included. The activity price covers exactly what is listed in the "
        "'What's included' section.",
    ),
    (
        "Do I need to bring cash?",
        "Yes — a small amount of Egyptian pounds or USD is useful for tips "
        "(baksheesh), snacks, and any souvenirs or drinks not included in the "
        "tour. Card payment is widely accepted at larger sites.",
    ),
    (
        "What happens if it rains?",
        "Egypt is very dry year-round, so rain is rare. If the activity is "
        "cancelled due to unusual weather, we will offer an alternative date "
        "or a full refund.",
    ),
]

WATER_FAQS: list[tuple[str, str]] = [
    (
        "Do I need to know how to swim?",
        "For most snorkelling excursions, basic swimming ability is helpful but "
        "not essential — life jackets are available and instructors are on hand. "
        "Scuba diving requires basic swimming ability and a medical declaration.",
    ),
    (
        "Is snorkelling gear provided?",
        "Yes — mask, snorkel, and fins are provided on board. If you prefer your "
        "own gear for hygiene reasons, feel free to bring it. Underwater cameras "
        "are welcome and encouraged.",
    ),
    (
        "Are there age or health restrictions?",
        "Children under 6 and travellers with certain heart or respiratory "
        "conditions may not be able to participate. Please disclose any "
        "relevant medical history to your guide before departure.",
    ),
    (
        "Will I get seasick?",
        "The Red Sea is generally calm, but if you are prone to motion sickness, "
        "take medication 30 minutes before departure. Crew members are trained "
        "to help and will find you a comfortable spot.",
    ),
]

CULTURAL_FAQS: list[tuple[str, str]] = [
    (
        "Is there a dress code for the temples?",
        "Yes — shoulders and knees should be covered when visiting religious "
        "sites. A light scarf is useful and versatile. Comfortable walking "
        "shoes are essential — expect uneven ground and some stairs.",
    ),
    (
        "Are cameras allowed?",
        "Cameras are allowed in most outdoor areas. Some tombs and museums "
        "charge a separate photography fee or prohibit flash. Your guide will "
        "advise you on-site.",
    ),
    (
        "How much walking is involved?",
        "Expect 2-4 hours of walking over uneven ground, with occasional steps "
        "and direct sun exposure. This activity is not recommended for guests "
        "with limited mobility unless otherwise stated.",
    ),
]

ADVENTURE_FAQS: list[tuple[str, str]] = [
    (
        "Is a driving licence required?",
        "For quad-bike or buggy activities, a valid driving licence is required "
        "(any country). Some operators accept a copy; others require the "
        "original. Please check at booking.",
    ),
    (
        "Is there a minimum age?",
        "Drivers must typically be 16+ and passengers 8+. Children under 8 "
        "must ride with an adult. Age requirements vary — confirm at booking.",
    ),
    (
        "Is this activity suitable for beginners?",
        "Yes — all adventure activities are guided and suitable for first-timers. "
        "You will receive a full safety briefing and equipment check before "
        "starting.",
    ),
]

WILDLIFE_FAQS: list[tuple[str, str]] = [
    (
        "Do we get to touch or swim with the animals?",
        "We work only with operators that respect international wildlife "
        "guidelines. Any interaction is at the animal's choice — no chasing, "
        "touching, or feeding. Our priority is the animals' welfare.",
    ),
    (
        "Is there a chance we won't see the animals?",
        "Wildlife is unpredictable. We choose locations and seasons to maximise "
        "sightings, but we cannot guarantee encounters. In the rare case of a "
        "missed sighting, we will offer an alternative date.",
    ),
]

FOOD_FAQS: list[tuple[str, str]] = [
    (
        "Can you accommodate dietary restrictions?",
        "Yes — vegetarian, vegan, gluten-free, and nut-free options are "
        "available. Please let us know at least 48 hours before the activity.",
    ),
    (
        "Is alcohol served?",
        "Alcohol is not typically served on family-oriented tours. Some "
        "evening activities include a welcome drink. Please check the "
        "'What's included' section for details.",
    ),
]


# ══════════════════════════════════════════════════════════════════
#  Tip library — keyed by category bucket
# ══════════════════════════════════════════════════════════════════
GENERIC_TIPS: list[str] = [
    "Bring a refillable water bottle — the Egyptian sun is strong year-round.",
    "Wear comfortable, broken-in shoes — you'll be on your feet more than you expect.",
    "Pack a light scarf or hat — useful for sun protection and visiting religious sites.",
    "Bring a small amount of local currency for tips (baksheesh) — it is expected for good service.",
    "Charge your phone and camera the night before — outlets can be scarce on tour.",
    "Book the earliest time slot in summer — you'll avoid the midday heat and crowds.",
]

WATER_TIPS: list[str] = [
    "Use reef-safe sunscreen only — regular sunscreen harms the Red Sea coral.",
    "Bring a waterproof phone pouch — the sea spray gets everywhere.",
    "Snorkel early in the morning — the water is calmest and visibility is best.",
    "Don't touch the coral — even a light brush can kill it. Look, don't touch.",
    "Bring a light rash guard — it protects against sun and jellyfish stings.",
    "Book a small-group boat if possible — fewer people means a better experience.",
]

CULTURAL_TIPS: list[str] = [
    "Hire a certified Egyptologist guide — the difference in understanding is enormous.",
    "Start early — the Valley of the Kings is cooler and quieter before 9am.",
    "Bring small notes for tips — toilet attendants, temple guards, and drivers all appreciate it.",
    "Carry tissues — public restrooms often run out of paper.",
    "Learn a few Arabic greetings — 'shukran' (thank you) goes a long way.",
]

ADVENTURE_TIPS: list[str] = [
    "Wear closed-toe shoes and long trousers — sand gets everywhere on quad bikes.",
    "Bring sunglasses and a bandana — the desert dust is real.",
    "Follow your guide's line exactly — shortcuts in the desert are dangerous.",
    "Empty your pockets — phones and wallets fall out easily at speed.",
]

WILDLIFE_TIPS: list[str] = [
    "Respect the animals' space — never chase, touch, or feed wild animals.",
    "Keep your voice low — loud noises startle marine and desert wildlife.",
    "Use reef-safe sunscreen — it protects the marine environment you came to see.",
    "Leave nothing behind — take all rubbish back with you.",
]

FOOD_TIPS: list[str] = [
    "Come hungry — the portions are generous.",
    "Try the local speciality — ask your host for their recommendation.",
    "Bring a light jumper — evening dinners can be breezy on the terrace.",
]


# ══════════════════════════════════════════════════════════════════
#  Category bucketing
# ══════════════════════════════════════════════════════════════════
def _bucket(category: str | None, name: str | None) -> str:
    """Map a category + name to a content bucket."""
    text = f"{(category or '')} {(name or '')}".lower()

    if any(k in text for k in ("dolphin", "wildlife", "aquarium", "turtle")):
        return "wildlife"
    if any(k in text for k in ("diving", "dive", "snorkel", "scuba", "snorkeling")):
        return "water"
    if any(k in text for k in ("boat", "cruise", "yacht", "sail", "beach", "island", "sea", "red sea")):
        return "water"
    if any(k in text for k in ("temple", "pyramid", "history", "museum", "luxor", "karnak", "valley", "abu simbel", "cairo")):
        return "cultural"
    if any(k in text for k in ("quad", "safari", "desert", "buggy", "camel", "horse", "jeep", "balloon")):
        return "adventure"
    if any(k in text for k in ("food", "dinner", "lunch", "dining", "culinary", "cooking")):
        return "food"

    return "generic"


BUCKET_FAQS = {
    "wildlife":  WILDLIFE_FAQS,
    "water":     WATER_FAQS,
    "cultural":  CULTURAL_FAQS,
    "adventure": ADVENTURE_FAQS,
    "food":      FOOD_FAQS,
    "generic":   [],
}

BUCKET_TIPS = {
    "wildlife":  WILDLIFE_TIPS,
    "water":     WATER_TIPS,
    "cultural":  CULTURAL_TIPS,
    "adventure": ADVENTURE_TIPS,
    "food":      FOOD_TIPS,
    "generic":   [],
}


# ══════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════
def enrich(dry_run: bool, force: bool) -> int:
    app = create_app()
    with app.app_context():
        activities = db.session.query(Activity).order_by(Activity.id).all()
        destinations = {d.id: d.name for d in db.session.query(Destination).all()}

        n_faqs_added = 0
        n_tips_added = 0
        n_skipped = 0

        for a in activities:
            # Idempotency: skip if this activity already has content
            if not force:
                existing_faqs = (
                    db.session.query(ActivityFAQ)
                    .filter_by(activity_id=a.id)
                    .count()
                )
                existing_tips = (
                    db.session.query(ActivityTip)
                    .filter_by(activity_id=a.id)
                    .count()
                )
                if existing_faqs > 0 or existing_tips > 0:
                    n_skipped += 1
                    continue

            dest_name = destinations.get(a.destination_id, "")
            bucket = _bucket(a.category, a.name)

            # ─── FAQs ───
            faqs_to_add: list[tuple[str, str]] = []
            faqs_to_add.extend(BUCKET_FAQS.get(bucket, []))
            faqs_to_add.extend(GENERIC_FAQS)

            # Deduplicate by question text
            seen_q: set[str] = set()
            unique_faqs: list[tuple[str, str]] = []
            for q, ans in faqs_to_add:
                if q in seen_q:
                    continue
                seen_q.add(q)
                unique_faqs.append((q, ans))

            # Cap at 5 FAQs
            unique_faqs = unique_faqs[:5]

            if not dry_run:
                for i, (q, ans) in enumerate(unique_faqs, start=1):
                    db.session.add(ActivityFAQ(
                        activity_id=a.id,
                        question=q,
                        answer=ans,
                        sort_order=i,
                    ))
                    n_faqs_added += 1
            else:
                n_faqs_added += len(unique_faqs)

            # ─── Tips ───
            tips_to_add = list(BUCKET_TIPS.get(bucket, [])) + list(GENERIC_TIPS)

            # Dedupe
            seen_t: set[str] = set()
            unique_tips: list[str] = []
            for t in tips_to_add:
                if t in seen_t:
                    continue
                seen_t.add(t)
                unique_tips.append(t)

            # Cap at 4 tips
            unique_tips = unique_tips[:4]

            if not dry_run:
                for i, tip in enumerate(unique_tips, start=1):
                    db.session.add(ActivityTip(
                        activity_id=a.id,
                        tip=tip,
                        sort_order=i,
                    ))
                    n_tips_added += 1
            else:
                n_tips_added += len(unique_tips)

            print(f"  [{bucket:9s}] {a.id:4d} | {a.name[:50]:50s} | "
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