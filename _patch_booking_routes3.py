path = "blueprints/public/booking_routes.py"
lines = open(path, "r", encoding="utf-8").read().splitlines(keepends=True)

# Locate the option_summary block
start = None
end = None
for i, ln in enumerate(lines):
    if "option_summary = None" in ln:
        start = i
    if start is not None and "currency\": price.currency if price else None," in ln:
        end = i
        # include the closing brace line
        if i + 1 < len(lines) and lines[i + 1].strip() == "}":
            end = i + 1
        break

assert start is not None and end is not None, f"markers not found: {start} {end}"

new_block = '''    option_summary = None
    if option is not None:
        from models import PackageFlight as _PF
        if isinstance(option, _PF):
            # PackageFlight card — pull display fields from outbound leg
            ob = option.outbound_flight
            airline_logo = None
            airline_name = None
            flight_from = None
            flight_to = None
            luggage = None
            if ob is not None:
                airline_name = getattr(ob, "airline", None)
                flight_from = getattr(ob, "origin", None)
                flight_to = getattr(ob, "destination", None)
                luggage = getattr(ob, "luggage_kg", None)
                if airline_name:
                    normalized = airline_name.strip().lower().replace(" ", "")
                    for a in db.session.scalars(select(Airline)):
                        if a.name and a.name.strip().lower().replace(" ", "") == normalized:
                            if a.logo_url:
                                airline_logo = a.logo_url
                            airline_name = a.name
                            break
            option_summary = {
                "id": option.id,
                "label": (
                    f"{airline_name or 'Flight'} "
                    f"{getattr(ob, 'departure_date', '') or ''}"
                ).strip(),
                "departure_date": getattr(ob, "departure_date", None) if ob else None,
                "return_date": (
                    getattr(option.inbound_flight, "departure_date", None)
                    if option.inbound_flight else None
                ),
                "flight_from": flight_from,
                "flight_to": flight_to,
                "airline_name": airline_name,
                "airline_logo": airline_logo,
                "luggage_allowance": luggage,
                "price_adult": pricing.get("adult_rate"),
                "price_child": pricing.get("child_rate"),
                "currency": pricing.get("currency"),
            }
        else:
            # Legacy PackageOption
            flight = getattr(option, "flight", None)
            price = getattr(option, "price", None)
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
                "label": getattr(option, "display_label", None),
                "departure_date": getattr(option, "departure_date", None),
                "return_date": getattr(option, "return_date", None),
                "flight_from": getattr(flight, "flight_from", None) if flight else None,
                "flight_to": getattr(flight, "flight_to", None) if flight else None,
                "airline_name": getattr(flight, "airline_name", None) if flight else None,
                "airline_logo": airline_logo,
                "luggage_allowance": getattr(flight, "luggage_allowance", None) if flight else None,
                "price_adult": float(price.adult_price) if price else None,
                "price_child": float(price.child_price) if price else None,
                "currency": price.currency if price else None,
            }
'''

lines[start:end+1] = [new_block]
open(path, "w", encoding="utf-8").writelines(lines)
print("option_summary block patched")