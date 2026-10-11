import re
p = 'blueprints/public/booking_routes.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

print("USD occurrences in booking_routes.py:")
print("=" * 70)
for i, m in enumerate(re.finditer(r'"USD"|\'USD\'', c), 1):
    line_no = c[:m.start()].count("\n") + 1
    line_start = c.rfind("\n", 0, m.start()) + 1
    line_end = c.find("\n", m.end())
    if line_end == -1:
        line_end = len(c)
    line = c[line_start:line_end].rstrip()
    print(f"{i}. line {line_no}: {line.strip()}")
    print(f"   Context: {c[max(0,m.start()-50):m.end()+50]!r}")

before = c.count('"USD"') + c.count("'USD'")

# Special case: fix the ternary first
ternary_old = 'currency = "EUR" if product_type in (PRODUCT_TYPE_HOTEL, PRODUCT_TYPE_PACKAGE) else "USD"'
ternary_new = 'currency = "EUR"  # all products priced in EUR'
if ternary_old in c:
    c = c.replace(ternary_old, ternary_new)
    print("\n✅ Ternary line replaced")

# Replace remaining "USD" with "EUR"
c = c.replace('"USD"', '"EUR"')
c = c.replace("'USD'", "'EUR'")

after = c.count('"USD"') + c.count("'USD'")

print(f"\nBefore: {before} occurrences")
print(f"After: {after} occurrences")

if before != after:
    with open(p, 'w', encoding='utf-8') as f:
        f.write(c)
    print("✅ FILE WRITTEN")
else:
    print("⚠️ NO CHANGES MADE")
