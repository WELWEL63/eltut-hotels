import os

# Force production config before importing app
os.environ.setdefault("FLASK_ENV", "production")

from app import create_app

# Create the app explicitly - if this fails, it will crash loudly with a clear error
app = create_app()