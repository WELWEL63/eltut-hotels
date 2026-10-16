p = 'blueprints/public/routes.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# ─── 1) Change _cheapest_per_destination to return dicts ───
old_ret = '''    # Sort by price ascending, take the top `limit`
    ordered = sorted(best.values(), key=lambda t: t[0])
    return [obj for _, obj in ordered[:limit]]'''

new_ret = '''    # Sort by price ascending, take the top `limit`
    ordered = sorted(best.values(), key=lambda t: t[0])
    # Return dicts with both the object and its cheapest price
    return [
        {"obj": obj, "price": round(float(price), 2)}
        for price, obj in ordered[:limit]
    ]'''

if old_ret in c:
    c = c.replace(old_ret, new_ret, 1)
    print("✅ Patch 1: _cheapest_per_destination returns dicts")
else:
    print("❌ Patch 1 failed: anchor not found")
    raise SystemExit(1)

# ─── 2) Update route to use new shape: extract .obj for count and pass through ───
# (The route itself doesn't need changes because it just passes to the template —
#  the template needs updating, but we do that separately.)

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print("✅ routes.py patched")
