import re
path = "blueprints/public/package_routes.py"
s = open(path, "r", encoding="utf-8").read()

anchor = "    return render_template(\n        \"public/package_detail.html\","
insert = '''    # Airline lookup for JS-side logo resolution (template reads it).
    airlines_by_name: dict[str, dict] = {}
    try:
        from models import Airline
        for al in db.session.scalars(select(Airline)):
            if al.name:
                normalized = al.name.strip().lower().replace(" ", "")
                airlines_by_name[normalized] = {
                    "name": al.name,
                    "logo_url": al.logo_url,
                }
    except Exception as exc:
        current_app.logger.debug("airline lookup failed: %s", exc)

'''
if insert.strip() not in s:
    s = s.replace(anchor, insert + anchor, 1)
    s = s.replace(
        "        options=options,\n        check_in=check_in,",
        "        options=options,\n        airline_lookup=airlines_by_name,\n        check_in=check_in,",
        1,
    )
    open(path, "w", encoding="utf-8").write(s)
    print("patched")
else:
    print("already patched")