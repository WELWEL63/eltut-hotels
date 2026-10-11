import time
from app import create_app
from extensions import db

app = create_app()
with app.test_client() as client:
    for path in ["/", "/hotels", "/packages", "/activities"]:
        # Warm-up (first request initializes things)
        client.get(path)
        # Timed request
        t0 = time.time()
        r = client.get(path)
        elapsed = time.time() - t0
        print(f"  {path:<15} → {elapsed*1000:>7.0f} ms  (status {r.status_code})")

    # Also test a single query in isolation
    with app.app_context():
        from sqlalchemy import select
        from models import Hotel
        t0 = time.time()
        db.session.execute(select(Hotel).limit(1)).first()
        print(f"\n  Single DB query  → {(time.time()-t0)*1000:>7.0f} ms")
