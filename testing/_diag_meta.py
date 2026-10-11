p = 'blueprints/public/booking_routes.py'
with open(p, encoding='utf-8') as f:
    c = f.read()
idx = c.find("if product_type == PRODUCT_TYPE_HOTEL")
if idx == -1:
    idx = c.find("product_type == PRODUCT_TYPE_HOTEL")
print("Found at char", idx)
print("=" * 70)
print(c[idx:idx + 900])
