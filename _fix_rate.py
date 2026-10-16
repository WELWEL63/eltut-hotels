import io
path = "services/package_pricing_service.py"
with io.open(path, encoding="utf-8") as f:
    c = f.read()

old = """        w_nights = max(1, (chosen.valid_to - chosen.valid_from).days) \\
            if (chosen.valid_from and chosen.valid_to) else 1
        return (float(chosen.adult_price) / w_nights, chosen.currency)"""

new = """        return (float(chosen.adult_price), chosen.currency)"""

if old in c:
    c = c.replace(old, new, 1)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("Fixed rate calculation")
else:
    print("Anchor not found")
