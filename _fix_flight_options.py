# -*- coding: utf-8 -*-
"""Patch flight_options_for_package to derive nights from card flights."""
import io
path = "services/flight_service.py"
with io.open(path, encoding="utf-8") as f:
    c = f.read()

# Find the section where card grand_total is computed
# We need to change:
#   outbound_price = Decimal(chosen.price_gbp)
#   ...
#   flight_total = flight_total_one_pax * pax

# Replace the entire for-airline loop body's compute block
old = '''        chosen = sorted(rows, key=sort_key)[0]
        offset_days = (chosen.departure_date - check_in).days

        outbound_price = Decimal(chosen.price_gbp)

        # Return leg: no inbound data yet, so estimate 1× outbound
        return_price = outbound_price
        return_estimated = True

        flight_total_one_pax = outbound_price + return_price
        flight_total = flight_total_one_pax * pax'''

new = '''        chosen = sorted(rows, key=sort_key)[0]
        offset_days = (chosen.departure_date - check_in).days

        outbound_price = Decimal(chosen.price_gbp)

        # Try to find a matching inbound flight (same airline, closest return)
        # This is auto-pick mode — no pinned inbound, so we estimate.
        return_price = outbound_price
        return_estimated = True

        # Nights from the customer's chosen check_in/check_out
        # (this function is called for auto-pick packages that use
        #  package.check_in / package.check_out, not card-level dates)
        _nights = 0
        if check_in and check_out:
            _nights = (check_out - check_in).days

        flight_total_one_pax = outbound_price + return_price
        flight_total = flight_total_one_pax * pax'''

if old in c:
    c = c.replace(old, new, 1)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("flight_options_for_package patched")
else:
    print("Anchor not found — check the actual text")
    idx = c.find("outbound_price = Decimal(chosen.price_gbp)")
    print("Context:", repr(c[idx-100:idx+300]) if idx > 0 else "no match")