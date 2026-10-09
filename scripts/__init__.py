"""
scripts/__init__.py
───────────────────
Command-line utilities for eltut-tours-platform.

Modules:
    seed_from_csv    populate the SQL database from data/*.csv
    create_admin     create (or reset) the admin account
    reset_db         drop and re-create all tables (dev only)

Run each as a module:

    python -m scripts.seed_from_csv
    python -m scripts.create_admin
    python -m scripts.reset_db --yes
"""
