# ElTut Tours — Project State

**Last updated:** 2026-10-16 (end of session)
**Working tree:** clean
**Latest commit:** `cf5aab0 feat: implement package destination search functionality`

---

## 1. Product overview

ElTut Tours is a Flask 3 / SQLAlchemy 2 booking platform for Egypt travel.
Three customer-facing product types:

| Product | Table | Pricing source |
|---|---|---|
| Hotel | `hotels` + `rooms` + `room_rates` | nightly rate × nights |
| Package | `packages` + `package_flights` cards | `compute_package_flight_card()` |
| Activity | `activities` + `activity_prices` | flat per-person |

Supporting surfaces: quotes (admin-issued), enquiries (MongoDB), reviews (MongoDB),
PayPal payments, admin panel, account area, cloud-function worker.

---

## 2. Current state

### Working end-to-end (verified)
- Public home, about, contact
- Hotels list + detail + booking + confirmation
- Packages list + detail + booking + confirmation
- Activities list + detail + booking + confirmation
- Auth (register / login / password reset / verify)
- Account (dashboard, bookings, cancel, profile)
- Admin (all sections except Reports chart edge cases)
- Search results (hotels / packages / activities) with shared filter sidebar

### Land-only packages
Packages that have zero `PackageFlight` cards (Sharm, Luxor, Nile Cruise)
render as **land-only**. Priced from room rate if available, else the
package's own `PackagePrice` row. Bookable. No fake flight data.

### Pricing is unified
Customer-facing numbers come from exactly one source per product type.
For packages that source is `services.package_pricing_service.compute_package_flight_card()`,
which is the same function the admin preview uses. Customer and admin agree to the penny.

Verified example — package 919, card 14, 31 Jan 2027 → 12 Feb 2027, 2 adults:
- Hotel: £386.64
- Flights: £338.00
- Markup 10%: £73.06
- Transfer: £6.00
- Tax 5%: £40.19
- **Per person: £843.89** → £1,687.78 total
- Matches admin page to the penny

---

## 3. Architecture

### Backend modules

    app.py                        Flask factory + Jinja globals + caches
    config.py                     Environment-driven config
    extensions.py                 db, login_manager, mail, csrf, migrate
    models/                       SQLAlchemy 2.x, 30 model files
    mongo/                        Reviews, enquiries, logs, search_events
    services/                     17 service modules (business logic)
    blueprints/public/            Customer-facing routes
    blueprints/admin/             Admin panel
    blueprints/auth/              Login / register / reset
    blueprints/account/           Customer account area
    blueprints/api/               JSON endpoints
    cloud_function/               Booking processing worker
    scripts/                      One-off and maintenance scripts
    migrations/                   Alembic revisions

### Frontend

    templates/base.html           Layout, nav, footer
    templates/public/             Public pages + shared partials
    static/css/eltut.css          Global styles
    static/css/search_results.css Search results page only

Templating: Jinja2. Styling: Bootstrap 5.3 + custom. No build step.

---

## 4. Session log — 2026-10-16

### Problem
The customer-facing package flow returned prices that did not match the
admin page. Four independent formulas existed across search, detail,
booking, and confirmation. Only one was correct.

### Root cause
`services/flight_service.flight_options_for_package()` **invented** options
from raw `flight_prices` rows, ignoring the `package_flights` cards the
admin had explicitly created. It also:
- Estimated the return leg as `outbound_price × 2` (wrong)
- Grouped by airline instead of by card (showed 1 of 4 cards)
- Ignored `PackageFlight.inbound_flight_id`

Three other formulas in `search_service._search_packages`,
`package_routes.package_detail` sidebar, and the confirmation template
also diverged.

### Fix — one authoritative source

    customer search ─┐
    customer detail ─┼─→ services.package_options_service.options_for_package()
    customer book   ─┤      ↓
    admin preview   ─┘   services.package_pricing_service.compute_package_flight_card()
                             ↓
                         PackageFlight card
                         (ob_outbound flight_prices id
                          + inbound flight_prices id)

### Files changed

**Backend**
- `migrations/versions/b1a2c3d4e5f6_add_is_bookable_to_destinations.py` (new)
- `models/destination.py` — added `is_bookable` boolean
- `services/package_pricing_service.py` — extended output with display keys
- `services/package_options_service.py` (new) — single option source + land-only fallback
- `services/search_service.py` — package pricing from cards, widget filter, total-after-filter fix
- `services/pricing_service.py` — accepts `package_flight_id`
- `services/flight_service.py` — deleted dead `flight_options_for_package`
- `blueprints/public/package_routes.py` — uses `options_for_package`
- `blueprints/public/booking_routes.py` — card-based pricing, enriched confirmation context
- `blueprints/public/search_routes.py` — passes `package_destinations`
- `app.py` — new Jinja global `search_package_destinations()`

**Frontend**
- `templates/public/_filters_sidebar.html` (new) — shared filter component
- `templates/public/booking_confirmation.html` — full rewrite (package + hotel + activity branches)
- `templates/public/booking_start.html` — sidebar shows hotel/room/meal plan/stars
- `templates/public/hotel_detail.html` — sidebar shows meal plan on room select
- `templates/public/hotel_list.html`, `package_list.html`, `activity_list.html` — wired shared sidebar
- `templates/public/search_results.html` — wired compact sidebar
- `templates/public/_search_widget.html` — package tab uses filtered destination list
- `templates/public/package_detail.html` — land-only UI guards

**Scripts**
- `scripts/set_destination_bookable.py` (new) — toggle destinations on/off by flight data
- `scripts/cleanup_legacy_flights.py` (new) — delete orphan mocked flight rows

**Data**
- Deleted 65 legacy `flights` rows in disabled destinations (Sharm, Luxor, Nile Cruise)
- Set `is_bookable=True` for all 16 destinations (initially disabled 10, then re-enabled all — the widget filter is now package-based instead)

### Cleanup
55 scratch `_*.py` files removed from project root.

---

## 5. Business rules locked

### Package pricing
    hotel_total   = room_nightly × card_nights
    flights_total = outbound.price_gbp + inbound.price_gbp
    subtotal      = hotel_total + flights_total
    markup        = (subtotal + transfer) × markup_pct / 100
    tax           = (subtotal + transfer + markup) × tax_pct / 100
    per_person    = subtotal + transfer + markup + tax

### Package availability
- Customer searches by destination + dates + party
- Cards whose outbound date is within ±3 days of `check_in` are shown
- Closest departure first, then cheapest
- If 0 cards exist → land-only option (hotel + transfer + markup + tax, no flight)
- If cards exist but none match dates → validation message, no book

### Search widget
- Hotels tab: all bookable destinations
- Packages tab: destinations with ≥1 active package
- Activities tab: all bookable destinations

### Booking
- Server always recomputes from `package_flight_id` — never trusts client prices
- Missing `package_flight_id` for a package → refused with warning

---

## 6. Known gaps / deferred

| Item | Priority | Notes |
|---|---|---|
| Price range slider on filters | Medium | Needs `min_price`/`max_price` on 4 routes + service filter |
| Egypt Travel Guide package (2172) | Low | 0 prices, junk name; delete or fix in admin |
| Package 2171 (Explore Egypt) | Low | Tagged CRUISE but destination=Hurghada; shows under Hurghada filter |
| Package flight card 17 (id 17) | Low | Inbound date 2028 (374 nights) — data entry error; skipped by `nights > 60` guard |
| Hotel "on request" for 6 Sharm packages | Low | Rooms have 0 rate + no RoomRate; only PackagePrice fallback |
| Test bookings in DB | Low | ELT-2026-98386, ELT-2026-76419, ELT-2026-93094, ELT-2026-62568 |
| No pytest suite | Medium | Only manual checks; health_check.py helps but is not a test suite |

---

## 7. Environment

- Python 3.12 (venv at `.venv/`)
- Flask 3, SQLAlchemy 2.0.32, Alembic 1.13.2, Flask-Migrate 4.x
- PostgreSQL 18.6 on Neon (eu-central-1)
- MongoDB Atlas for reviews / enquiries / logs / search_events
- PayPal REST (sandbox placeholder in dev)
- IONOS SMTP (placeholder in dev)

### Jinja globals registered in `app.py`
- `now()` — datetime helper
- `search_destinations()` — all bookable destinations (cached per request)
- `search_package_destinations()` — bookable destinations with ≥1 active package (cached)
- `slideshow_slides()` — home page slideshow data
- `maybe_url()` — safe `url_for` fallback
- `content()` — CMS content lookup
- `csrf_token()` — from Flask-WTF

### Scripts reference
    python -m scripts.set_destination_bookable              # dry-run
    python -m scripts.set_destination_bookable --commit
    python -m scripts.cleanup_legacy_flights                # dry-run
    python -m scripts.cleanup_legacy_flights --commit
    python -m scripts.health_check                          # project health

---

## 8. Testing checklist

After any change to packages / pricing / booking:

1. Open `/packages/hurghada-albatross-palace-beach-resort-standard-room-pool-garden-view-2?check_in=2027-01-31&check_out=2027-02-12&adults=2&children=0`
2. Verify total = **£1,687.78** for 2 adults
3. Click **Book this departure** → booking form should show **£1,687.78**
4. Complete booking → confirmation should show **£1,687.78**
5. Compare with `/admin/packages/919/edit` → price breakdown table (row 1) → **£843.89 per person**

If any of the three disagree, the fix is broken.

For hotels:
- `/hotels/coral-sun-beach?check_in=2027-01-22&check_out=2027-01-29&adults=2` → select a room
- Sidebar shows room name, meal plan, price, nights
- Book → confirmation shows same numbers

For activities:
- Pick any activity → book → confirmation shows activity name + duration + inclusions

---

## 9. Contact / handover notes

- Rotate the Neon DB password and any real PayPal/SMTP secrets before sharing this project
- The `.env.example` file documents every required variable
- The `.env` file must never be committed (already in `.gitignore`)
- All Alembic revisions live in `migrations/versions/`; current head: `b1a2c3d4e5f6`