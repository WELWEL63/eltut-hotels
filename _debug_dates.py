import io
path = "blueprints/admin/package_admin.py"
with io.open(path, encoding="utf-8") as f:
    c = f.read()

# 1. Fix hotel select id in template
tpl_path = "templates/admin/package_form.html"
with io.open(tpl_path, encoding="utf-8") as f:
    t = f.read()

old_hotel = '<select name="hotel_id" class="form-select" required>'
new_hotel = '<select name="hotel_id" id="pkg-hotel-id" class="form-select" required>'

if 'id="pkg-hotel-id"' in t:
    print("Hotel id already present")
elif old_hotel in t:
    t = t.replace(old_hotel, new_hotel, 1)
    with io.open(tpl_path, "w", encoding="utf-8") as f:
        f.write(t)
    print("Hotel id ADDED to template")
else:
    print("Hotel select not found")
    idx = t.find('name="hotel_id"')
    print("Debug:", repr(t[idx-50:idx+100]) if idx > 0 else "no match")

# 2. Add debug logging inside _apply_form_to_package
marker = '    package.check_in = _parse_date("check_in")'
if marker in c:
    debug_code = '''    import logging
    _raw_ci = (f.get("check_in") or "").strip()
    _raw_co = (f.get("check_out") or "").strip()
    logging.getLogger("admin").warning("DEBUG check_in raw=%r parsed=%r", _raw_ci, _parse_date("check_in"))
    package.check_in = _parse_date("check_in")'''
    if 'DEBUG check_in raw' not in c:
        c = c.replace(marker, debug_code, 1)
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(c)
        print("Debug logging added")
    else:
        print("Debug already in place")
else:
    print("check_in save line not found")