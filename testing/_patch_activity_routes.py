p = 'blueprints/public/activity_routes.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# Replace the final render_template block with enriched version
old = '''    return render_template(
        "public/activity_detail.html",
        activity=activity,
        destination=destination,
        guide=guide,
        images=images,
        inclusions=inclusions,
        exclusions=exclusions,
        languages=languages,
        price_adult=price_adult,
        price_child=price_child,
        currency=currency,
        avg_rating=avg_rating,
        review_count=review_count,
        remaining=remaining,
        related=related,
        reviews=reviews,
        user_has_reviewed=user_has_reviewed,
    )'''

new = '''    # ─── Read booking params from URL (fallback: today+7) ───
    from datetime import date as _date, timedelta as _td  # noqa: PLC0415

    def _parse_date_arg(name: str):
        raw = (request.args.get(name) or "").strip()
        if not raw:
            return None
        try:
            return _date.fromisoformat(raw)
        except ValueError:
            return None

    # Accept either ?date= or ?activity_date=
    activity_date = _parse_date_arg("date") or _parse_date_arg("activity_date")
    if not activity_date:
        activity_date = _date.today() + _td(days=7)

    adults = _int_arg("adults", 2, 1, 8)
    children = _int_arg("children", 0, 0, 8)

    # ─── Compute total for the party ───
    sidebar_pricing = {
        "adult_rate": price_adult,
        "child_rate": price_child,
        "nights": None,
        "total": None,
        "currency": currency or "EUR",
    }
    if price_adult is not None:
        child_rate = price_child or 0
        total = (float(price_adult) * adults) + (float(child_rate) * children)
        sidebar_pricing["total"] = total

    return render_template(
        "public/activity_detail.html",
        activity=activity,
        destination=destination,
        guide=guide,
        images=images,
        inclusions=inclusions,
        exclusions=exclusions,
        languages=languages,
        price_adult=price_adult,
        price_child=price_child,
        currency=currency,
        avg_rating=avg_rating,
        review_count=review_count,
        remaining=remaining,
        related=related,
        reviews=reviews,
        user_has_reviewed=user_has_reviewed,
        # NEW:
        activity_date=activity_date,
        adults=adults,
        children=children,
        sidebar_pricing=sidebar_pricing,
    )'''

if old in c:
    c = c.replace(old, new, 1)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(c)
    print("✅ activity_routes.py patched")
else:
    print("❌ PATTERN NOT FOUND")
    idx = c.find('"public/activity_detail.html"')
    print("Context:", repr(c[idx-200:idx+700]))
    raise SystemExit(1)
