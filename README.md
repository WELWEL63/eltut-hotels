# ElTut Tours

A Flask + PostgreSQL + MongoDB booking platform for Egypt travel — hotels, packages, and activities. Includes a full admin panel, customer accounts, quote workflow, PayPal payments, and a background worker for post-booking tasks.

---

## Requirements

- Python 3.12 (3.11 also works)
- PostgreSQL 15+ (production uses Neon, eu-central-1)
- MongoDB Atlas (reviews, enquiries, activity logs, search analytics)
- SMTP account (IONOS or any provider) for transactional email
- PayPal REST credentials (sandbox for dev, live for production)

---

## Quick start (local development)

    git clone <repo-url> eltut-tours-platform
    cd eltut-tours-platform

    python -m venv .venv
    # Windows: .venv\Scripts\activate
    # macOS/Linux: source .venv/bin/activate

    pip install -r requirements.txt
    cp .env.example .env
    flask db upgrade
    python -m scripts.seed_from_csv --file all
    python -m scripts.create_admin
    flask run

App starts on http://127.0.0.1:5000

---

## Environment variables

Every variable is documented in .env.example. Essentials:

| Variable | Purpose |
|---|---|
| FLASK_APP | Must be app.py |
| FLASK_ENV | development or production |
| SECRET_KEY | Session signing key - long random hex |
| DATABASE_URL | PostgreSQL connection string |
| MONGO_URI | MongoDB Atlas URI |
| MONGO_DB_NAME | Mongo database name |
| MAIL_* | IONOS SMTP settings |
| PAYPAL_* | PayPal REST client credentials |
| ADMIN_EMAIL / ADMIN_PASSWORD | Seeded admin account |
| APP_BASE_URL | Public URL, used in emails |

The app boots without real Mongo / SMTP / PayPal credentials — those features gracefully no-op and log a warning. Only SECRET_KEY and DATABASE_URL are required.

---

## Project layout

    app.py                    Flask factory, Jinja globals, error handlers
    config.py                 Configuration classes
    extensions.py             db, login_manager, mail, csrf, migrate
    utils.py                  Shared helpers + Jinja filters

    models/                   SQLAlchemy models (30 files)
    services/                 Business logic (17 files, no Flask coupling)
    blueprints/               Routes (public / admin / auth / account / api)
    mongo/                    MongoDB repositories (reviews / enquiries / logs)
    cloud_function/           Booking worker (email + log + history)

    templates/                Jinja2 templates
    static/                   CSS, JS, images, uploads
    migrations/               Alembic revisions
    scripts/                  Maintenance and seed scripts
    data/                     CSV sources for seeding

---

## Common commands

    flask run

    flask db migrate -m "description"
    flask db upgrade
    flask db downgrade

    python -m scripts.seed_from_csv --file all --dry-run
    python -m scripts.seed_from_csv --file hotels

    python -m scripts.create_admin
    python -m scripts.create_admin --force --role admin --email you@example.com

    python -m scripts.set_destination_bookable                # dry-run
    python -m scripts.set_destination_bookable --commit

    python -m scripts.cleanup_legacy_flights                  # dry-run
    python -m scripts.cleanup_legacy_flights --commit

    python -m scripts.reset_db --truncate --yes

    python -m scripts.health_check

---

## The three product types

### Hotels
Browsed via /hotels, filtered by destination / stars / meal plan / dates. Detail page shows rooms + seasonal rates from room_rates. Booking selects a room; server prices as nightly x nights x party.

### Packages
Browsed via /packages, filtered by destination / type / min nights / dates. A package bundles hotel + room + flights (as PackageFlight cards) + transfer + markup + tax. Each PackageFlight card pairs one outbound flight with one inbound flight. Customer chooses a card; server prices from compute_package_flight_card().

Packages with zero cards render as land-only — no flights, still bookable. See PROJECT_STATE.md sections 4-5 for the full pricing contract.

### Activities
Browsed via /activities, filtered by destination / category / difficulty. Flat per-person pricing from activity_prices. Capacity enforced via availability_service.

---

## Search

/search redirects to /search/results preserving the query string. Results page shows:

- A persistent widget at the top (destination / dates / party / type)
- A compact filter sidebar on the left (stars, meal plan, category, difficulty, min nights, keyword, sort)

Query parameters:

| Param | Meaning |
|---|---|
| type | hotel or package or activity |
| destination | destination slug |
| check_in / check_out | ISO dates (hotels + packages) |
| date | ISO date (activities) |
| adults / children | party size, capped at 8 each |
| sort | newest or name or price_asc or price_desc or stars_desc or duration_asc |
| q | free-text search on product name |

---

## Admin panel

URL prefix: /admin (login required, role admin).

Sections: Dashboard, Activities, Hotels, Packages, Bookings, Quotes, Users, Reviews, Enquiries, Reports, Media, Site content, Airlines, Flight prices, Hotel CSV importer, Offers.

---

## Deployment

Target: any WSGI host supporting Python 3.12 + PostgreSQL. Repo includes Procfile and render.yaml.

Required production env:

- FLASK_ENV=production
- SECRET_KEY (>= 32 random bytes hex)
- SESSION_COOKIE_SECURE=True
- DATABASE_URL (with sslmode=require)
- Real MAIL_* / PAYPAL_* credentials
- MONGO_URI if reviews/enquiries should persist

Run migrations on deploy: flask db upgrade

---

## Testing

No automated test suite yet. Two manual safety nets:

1. python -m scripts.health_check — verifies environment, DB connectivity, model/migration alignment, referential integrity, security hygiene. Read-only. Run after every deploy.

2. Package pricing cross-check — after any pricing change, verify this chain produces the same number:

       /packages/<hurghada-slug>?check_in=2027-01-31&check_out=2027-02-12&adults=2
         -> detail page total
         -> booking form total
         -> confirmation total
         -> admin /admin/packages/919/edit -> price breakdown row 1

   All four must show GBP 1,687.78. If any disagrees, pricing is broken.

---

## Further reading

- PROJECT_STATE.md — the complete session log, business rules, and known gaps. Read this before making changes to pricing or booking.
- migrations/versions/ — every schema change.

---

## License

Proprietary — ElTut Tours.







python -m scripts.session_report > _session_context.txt
Get-Content _session_context.txt
