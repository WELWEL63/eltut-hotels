import io
path = "blueprints/admin/package_admin.py"
with io.open(path, encoding="utf-8") as f:
    c = f.read()

# Anchor: end of _apply_form_to_package, right before google_maps_url
anchor = '''    package.google_maps_url = (f.get("google_maps_url") or "").strip() or None
'''

insert = '''    package.google_maps_url = (f.get("google_maps_url") or "").strip() or None

    # Fixed trip dates
    def _parse_date(key):
        from datetime import date as _date
        raw = (f.get(key) or "").strip()
        if not raw:
            return None
        try:
            return _date.fromisoformat(raw)
        except ValueError:
            return None

    package.check_in = _parse_date("check_in")
    package.check_out = _parse_date("check_out")
'''

if "package.check_in = _parse_date" in c:
    print("Already patched")
elif anchor in c:
    c = c.replace(anchor, insert, 1)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("Date save added to _apply_form_to_package")
else:
    print("Anchor not found")
    # Try fallback: find the end of _apply_form_to_package
    marker = "package.google_maps_url"
    idx = c.find(marker)
    print("Debug - context:", repr(c[idx-30:idx+80]) if idx > 0 else "no marker")