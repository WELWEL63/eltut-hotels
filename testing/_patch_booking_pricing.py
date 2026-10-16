p = 'blueprints/public/booking_routes.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# Find the pricing dispatch block
old = '''        if product_type == PRODUCT_TYPE_HOTEL:
            pricing = _room_stay_pricing(product, check_in, check_out, adults, children)
        elif product_type == PRODUCT_TYPE_PACKAGE:
            pricing = _package_pricing(product, adults, children)
        elif product_type == PRODUCT_TYPE_ACTIVITY:
            pricing = _activity_pricing(product, adults, children)
        else:
            pricing = {}'''

new = '''        if product_type == PRODUCT_TYPE_HOTEL:
            pricing = _room_stay_pricing(product, check_in, check_out, adults, children)
        elif product_type == PRODUCT_TYPE_PACKAGE:
            # If a specific departure option was selected, use ITS price.
            # Otherwise fall back to the package's first price row.
            if option is not None and option.price is not None:
                _adult = float(option.price.adult_price or 0)
                _child = float(option.price.child_price or 0)
                pricing = {
                    "adult_rate": _adult,
                    "child_rate": _child,
                    "nights": product.duration_nights,
                    "per_night": None,
                    "per_person": _adult,
                    "total": (_adult * adults) + (_child * children),
                    "currency": option.price.currency or "EUR",
                }
            else:
                pricing = _package_pricing(product, adults, children)
        elif product_type == PRODUCT_TYPE_ACTIVITY:
            pricing = _activity_pricing(product, adults, children)
        else:
            pricing = {}'''

if old in c:
    c = c.replace(old, new, 1)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(c)
    print("PATCHED - booking_routes.py uses option price when option_id present")
else:
    print("ANCHOR NOT FOUND")
    idx = c.find("_package_pricing(product")
    if idx >= 0:
        print("Context:")
        print(repr(c[max(0,idx-300):idx+300]))
    raise SystemExit(1)
