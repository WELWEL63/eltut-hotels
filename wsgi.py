import os
from app import create_app

# Force production config
os.environ.setdefault("FLASK_ENV", "production")

app = create_app()