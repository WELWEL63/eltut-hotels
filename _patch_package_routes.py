p = 'blueprints/public/package_routes.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# Find the return render_template block for package_detail
old = '''    return render_template(
        "public/package_detail.html",
        package=package,
        destination=destination,
        hotel=hotel,
        room=room,
        images=images,
        inclusions=inclusions,
        exclusions=exclusions,
        itineraries=itineraries,
        flights=flights,
        price_adult=price_adult,
        price_child=price_child,
        currency=currency,
        avg_rating=avg_rating,
        review_count=review_count,
        remaining=remaining,
        related=related,
        reviews=reviews,
        user_has_reviewed=user_has_reviewed,
        options=options,
        airline_lookup=airline_lookup,
    )'''

new = '''    # ─── Read stay params from URL (fallback: today → today+30) ───
    from datetime import date as _date, timedelta as _td  # noqa: PLC0415

    def _parse_date_arg(name: str):
        raw = (request.args.get(name) or "").strip()
        if not raw:
            return None
        try:
            return _date.fromisoformat(raw)
        except ValueError:
            return None

    url_check_in = _parse_date_arg("check_in")
    url_check_out = _parse_date_arg("check_out")

    if url_check_in and url_check_out and url_check_out > url_check_in:
        check_in = url_check_in
        check_out = url_check_out
    else:
        # Default to a future date so a booking can still be made
        check_in = _date.today() + _td(days=30)
        check_out = check_in + _td(days=package.duration_nights or 7)

    nights = max(1, (check_out - check_in).days) if check_in and check_out else (package.duration_nights or 7)
    adults = _int_arg("adults", 2, 1, 8)
    children = _int_arg("children", 0, 0, 8)

    # ─── Compute price for the specific stay (per-person, whole package) ───
    sidebar_pricing = {
        "adult_rate": price_adult,
        "child_rate": price_child,
        "nights": nights,
        "total": None,
        "currency": currency or "EUR",
    }
    if price_adult is not None:
        child_rate = price_child or 0
        total = (float(price_adult) * adults) + (float(child_rate) * children)
        sidebar_pricing["total"] = total
        sidebar_pricing["per_person"] = price_adult

    return render_template(
        "public/package_detail.html",
        package=package,
        destination=destination,
        hotel=hotel,
        room=room,
        images=images,
        inclusions=inclusions,
        exclusions=exclusions,
        itineraries=itineraries,
        flights=flights,
        price_adult=price_adult,
        price_child=price_child,
        currency=currency,
        avg_rating=avg_rating,
        review_count=review_count,
        remaining=remaining,
        related=related,
        reviews=reviews,
        user_has_reviewed=user_has_reviewed,
        options=options,
        airline_lookup=airline_lookup,
        # NEW:
        check_in=check_in,
        check_out=check_out,
        nights=nights,
        adults=adults,
        children=children,
        sidebar_pricing=sidebar_pricing,
    )'''

if old in c:
    c = c.replace(old, new, 1)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(c)
    print("✅ package_routes.py patched")
else:
    print("❌ PATTERN NOT FOUND")
    idx = c.find('"public/package_detail.html"')
    print("Context around render_template:", repr(c[idx-200:idx+800]))
    raise SystemExit(1)
