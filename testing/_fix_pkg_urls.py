p = 'templates/public/package_detail.html'
with open(p, encoding='utf-8') as f:
    c = f.read()

# ─── Fix 1: hero "Book now" (line 76) ───
old1 = "url_for('public.booking_start', product_type='package', product_id=package.id) }}{% if check_in %}&check_in={{ check_in.isoformat() }}{% endif %}"
new1 = "url_for('public.booking_start', product_type='package', product_id=package.id) }}?{% if check_in %}check_in={{ check_in.isoformat() }}{% endif %}"

count1 = c.count(old1)
if count1 > 0:
    c = c.replace(old1, new1)
    print(f"✅ Fix 1: {count1} occurrence(s) replaced")
else:
    print("❌ Fix 1: pattern not found")

# Also fix the sidebar one (line 631) if it has a slightly different indentation
# Same pattern, same replacement — should be caught by Fix 1 above

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)

print("✅ DONE")
