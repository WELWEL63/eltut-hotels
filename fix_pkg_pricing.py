import io
import re

path = "blueprints/public/booking_routes.py"
with io.open(path, "r", encoding="utf-8") as f:
    content = f.read()

func_pattern = re.compile(
    r'def _package_pricing\(.*?\n(?:    .*\n|\n)*?(?=^def |\Z)',
    re.DOTALL | re.MULTILINE
)

match = func_pattern.search(content)
if not match:
    print("Could not find _package_pricing in booking_routes.py.")
    exit()

new_func = '''def _package_pricing(
    package: Package,
    adults: int,
    children: int,
    package_flight_id: int | None = None,
) -> dict:
    """
    Price a package booking using the SAME engine the detail page uses.
    """
    empty = {
        "adult_rate": None, "child_rate": None, "nights": package.duration_nights,
        "per_night": None, "per_person": None, "total": None, "currency": "GBP",
        "package_flight_id": None,
        "hotel_total": None, "flight_total": None, "markup": None, "tax": None,
        "transfer_fee": None,
        "departure_date": None, "return_date": None,
        "airline_name": None, "airline_logo": None,
        "flight_from": None, "flight_to": None,
        "is_land_only": False,
    }

    from services.package_options_service import options_for_package

    try:
        options = options_for_package(
            package,
            check_in=None,
            check_out=None,
            adults=adults,
            children=children,
            tolerance_days=30,
        )
    except Exception as exc:
        current_app.logger.warning("options_for_package failed: %s", exc)
        options = []

    if not options:
        return empty

    chosen = None
    if package_flight_id:
        for opt in options:
            if opt.get("package_flight_id") == package_flight_id:
                chosen = opt
                break
    if chosen is None:
        chosen = options[0]

    pax = max(1, int(adults) + int(children))
    per_person = float(chosen.get("per_person") or 0.0)
    grand_total = float(chosen.get("grand_total") or (per_person * pax))
    if grand_total <= 0 and per_person > 0:
        grand_total = per_person * pax

    return {
        "adult_rate": round(per_person, 2),
        "child_rate": round(per_person, 2),
        "nights": int(chosen.get("nights") or package.duration_nights),
        "per_night": None,
        "per_person": round(per_person, 2),
        "total": round(grand_total, 2),
        "currency": chosen.get("currency") or "GBP",
        "package_flight_id": chosen.get("package_flight_id"),
        "hotel_total": round(float(chosen.get("land_total") or 0.0), 2),
        "flight_total": round(float(chosen.get("flight_total") or 0.0), 2),
        "markup": round(float(chosen.get("markup") or 0.0), 2),
        "tax": round(float(chosen.get("tax") or 0.0), 2),
        "transfer_fee": round(float(chosen.get("transfer_fee") or 0.0), 2),
        "departure_date": chosen.get("departure_date"),
        "return_date": chosen.get("return_date"),
        "airline_name": chosen.get("airline_name"),
        "airline_logo": chosen.get("airline_logo"),
        "flight_from": chosen.get("flight_from"),
        "flight_to": chosen.get("flight_to"),
        "is_land_only": bool(chosen.get("is_land_only")),
    }


'''

content = content[:match.start()] + new_func + content[match.end():]

with io.open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Replaced _package_pricing with a version that uses options_for_package.")