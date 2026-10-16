# -*- coding: utf-8 -*-
import io
path = "services/package_pricing_service.py"
with io.open(path, encoding="utf-8") as f:
    c = f.read()

# Replace the whole compute_package_flight_card function body
old_start = "def compute_package_flight_card(package, card):"
old_end = "def build_package_rows("

start = c.find(old_start)
end = c.find(old_end, start)

if start < 0 or end < 0:
    print("Anchors not found")
    raise SystemExit

new_func = '''def compute_package_flight_card(package, card):
    """Return dict with full breakdown for ONE PackageFlight card.

    Nights are derived from the card's own flight dates when BOTH
    outbound and inbound are set (flight-included package). If only
    outbound exists (land-only), nights fall back to package base dates.

    Keys: check_in, check_out, nights, room_nightly, currency,
          hotel_total, outbound_price, inbound_price, flight_total,
          subtotal, markup, tax, per_person, ok, error, land_only
    """
    result = {
        "ok": False, "error": None, "land_only": False,
        "check_in": None, "check_out": None, "nights": 0,
        "room_nightly": None, "currency": "GBP",
        "hotel_total": 0.0, "outbound_price": 0.0, "inbound_price": 0.0,
        "flight_total": 0.0, "subtotal": 0.0,
        "markup": 0.0, "tax": 0.0, "per_person": 0.0,
    }

    ob = card.outbound_flight
    ib = card.inbound_flight

    # Determine nights + effective dates
    if ob and ib and ob.departure_date and ib.departure_date:
        # Flight-included: nights from flight dates
        check_in = ob.departure_date
        check_out = ib.departure_date
        nights = (check_out - check_in).days
        result["land_only"] = False
    elif ob and not ib and package.check_in and package.check_out:
        # Land-only: no return, use package base dates
        check_in = package.check_in
        check_out = package.check_out
        nights = (check_out - check_in).days
        result["land_only"] = True
    else:
        result["error"] = "Missing dates"
        return result

    if nights <= 0:
        result["error"] = "Invalid dates"
        return result

    result["check_in"] = check_in
    result["check_out"] = check_out
    result["nights"] = nights

    # Room rate for those dates
    nightly, cur = _rate_for_room(package.room_id, check_in, check_out)
    if nightly is None:
        result["error"] = "No room rate"
        return result
    result["room_nightly"] = nightly
    if cur:
        result["currency"] = cur
    hotel_total = nightly * nights

    # Flights
    ob_price = float(ob.price_gbp) if ob else 0.0
    ib_price = float(ib.price_gbp) if ib else 0.0
    flight_total = ob_price + ib_price

    subtotal = hotel_total + flight_total
    transfer_fee = float(package.transfer_fee or 0)

    # Markup
    markup = 0.0
    if package.markup_value:
        mv = float(package.markup_value)
        if package.markup_kind == "percent":
            markup = (subtotal + transfer_fee) * (mv / 100.0)
        else:
            markup = mv

    # Tax
    tax = 0.0
    if package.tax_value:
        tv = float(package.tax_value)
        if package.tax_kind == "percent":
            tax = (subtotal + transfer_fee + markup) * (tv / 100.0)
        else:
            tax = tv

    per_person = subtotal + transfer_fee + markup + tax

    result.update({
        "ok": True,
        "outbound_price": ob_price,
        "inbound_price": ib_price,
        "flight_total": flight_total,
        "hotel_total": hotel_total,
        "transfer_fee": transfer_fee,
        "subtotal": subtotal,
        "markup": markup,
        "tax": tax,
        "per_person": per_person,
    })
    return result


'''

c = c[:start] + new_func + c[end:]

with io.open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("compute_package_flight_card rewritten")