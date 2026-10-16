p = 'blueprints/public/booking_routes.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# Extend option_summary to include airline_logo
old = '''    option_summary = None
    if option is not None:
        flight = option.flight
        price = option.price
        option_summary = {
            "id": option.id,
            "label": option.display_label,
            "departure_date": option.departure_date,
            "return_date": option.return_date,
            "flight_from": flight.flight_from if flight else None,
            "flight_to": flight.flight_to if flight else None,
            "airline_name": flight.airline_name if flight else None,
            "luggage_allowance": flight.luggage_allowance if flight else None,
            "price_adult": float(price.adult_price) if price else None,
            "price_child": float(price.child_price) if price else None,
            "currency": price.currency if price else None,
        }'''

new = '''    option_summary = None
    if option is not None:
        flight = option.flight
        price = option.price
        # Resolve airline logo (best-effort via Airline FK, then name match)
        airline_logo = None
        if flight is not None:
            try:
                if getattr(flight, "airline_id", None):
                    al = db.session.get(Airline, flight.airline_id)
                    if al and al.logo_url:
                        airline_logo = al.logo_url
                if airline_logo is None and flight.airline_name:
                    normalized = flight.airline_name.strip().lower().replace(" ", "")
                    for a in db.session.scalars(select(Airline)):
                        if a.name and a.name.strip().lower().replace(" ", "") == normalized:
                            airline_logo = a.logo_url
                            break
            except Exception:
                airline_logo = None

        option_summary = {
            "id": option.id,
            "label": option.display_label,
            "departure_date": option.departure_date,
            "return_date": option.return_date,
            "flight_from": flight.flight_from if flight else None,
            "flight_to": flight.flight_to if flight else None,
            "airline_name": flight.airline_name if flight else None,
            "airline_logo": airline_logo,
            "luggage_allowance": flight.luggage_allowance if flight else None,
            "price_adult": float(price.adult_price) if price else None,
            "price_child": float(price.child_price) if price else None,
            "currency": price.currency if price else None,
        }'''

if old in c:
    c = c.replace(old, new, 1)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(c)
    print("✅ booking_routes.py patched — option_summary has airline_logo")
else:
    print("❌ PATTERN NOT FOUND")
    idx = c.find("option_summary = None")
    print("Context:", repr(c[max(0,idx-100):idx+500]))
    raise SystemExit(1)
