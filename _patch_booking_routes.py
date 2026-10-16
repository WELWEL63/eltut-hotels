path = "templates/public/package_detail.html"
s = open(path, "r", encoding="utf-8").read()

old = "params.set('option_id', optionId);"
new = "params.set('package_flight_id', optionId);"

if old in s:
    s = s.replace(old, new, 1)
    open(path, "w", encoding="utf-8").write(s)
    print("patched option_id -> package_flight_id")
else:
    print("marker not found")