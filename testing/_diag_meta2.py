p = 'blueprints/public/booking_routes.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# Find the start of the hotel branch
idx = c.find('if product_type == PRODUCT_TYPE_HOTEL:')
if idx == -1:
    idx = c.find("if product_type == PRODUCT_TYPE_HOTEL:")
print("Found hotel branch at char", idx)
print("=" * 70)
# Show 800 chars from the SECOND occurrence (the one inside _product_meta)
idx2 = c.find('if product_type == PRODUCT_TYPE_HOTEL:', idx + 10)
if idx2 == -1:
    idx2 = idx
print(f"Second occurrence at {idx2}")
print(c[idx2:idx2 + 900])
