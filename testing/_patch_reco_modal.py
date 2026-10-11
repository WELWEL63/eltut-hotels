p = 'services/recommendation_service.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# Find the return dict inside _to_public_dict
old = '''    return {
        "id": activity.id,
        "code": activity.code,
        "name": activity.name,
        "slug": activity.slug,
        "category": activity.category,
        "difficulty": activity.difficulty,
        "duration_hours": (
            float(activity.duration_hours)
            if activity.duration_hours is not None
            else None
        ),
        "capacity": activity.capacity,
        "destination_id": activity.destination_id,
        "price_adult": adult_price,
        "price_child": child_price,
        "currency": currency,
        "image_url": _first_image_url(activity.id),
        "avg_rating": avg_rating,
        "score": _score(avg_rating, activity.capacity or 0),
    }'''

new = '''    # Trim description for the modal (first 400 chars, word boundary)
    desc_raw = activity.description or ""
    if len(desc_raw) > 400:
        desc_short = desc_raw[:400].rsplit(" ", 1)[0] + "..."
    else:
        desc_short = desc_raw

    return {
        "id": activity.id,
        "code": activity.code,
        "name": activity.name,
        "slug": activity.slug,
        "category": activity.category,
        "difficulty": activity.difficulty,
        "duration_hours": (
            float(activity.duration_hours)
            if activity.duration_hours is not None
            else None
        ),
        "capacity": activity.capacity,
        "destination_id": activity.destination_id,
        "price_adult": adult_price,
        "price_child": child_price,
        "currency": currency,
        "image_url": _first_image_url(activity.id),
        "avg_rating": avg_rating,
        "score": _score(avg_rating, activity.capacity or 0),
        # Modal fields
        "description": desc_short,
        "departure_time": activity.departure_time,
        "return_time": activity.return_time,
        "meeting_point": activity.meeting_point,
        "what_to_bring": activity.what_to_bring,
        "min_age": activity.min_age,
        "max_age": activity.max_age,
    }'''

if old in c:
    c = c.replace(old, new, 1)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(c)
    print("✅ recommendation_service.py patched")
else:
    print("❌ PATTERN NOT FOUND")
    # Diagnostic
    idx = c.find('"id": activity.id,')
    if idx >= 0:
        print("Context around found anchor:")
        print(repr(c[idx - 50:idx + 500]))
    raise SystemExit(1)
