p = 'blueprints/public/booking_routes.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

old = '''from models import (
    Activity,
    ActivityPrice,
    Booking,'''

new = '''from models import (
    Activity,
    ActivityPrice,
    Airline,
    Booking,'''

if old in c:
    c = c.replace(old, new, 1)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(c)
    print("✅ Airline imported")
else:
    print("❌ Anchor not found")
    raise SystemExit(1)
