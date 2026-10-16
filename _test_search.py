from datetime import date
from app import create_app
from extensions import db
from services import search_service

app = create_app()
ctx = app.app_context()
ctx.push()

r = search_service.search(
    product_type="package",
    destination="hurghada",
    check_in=date(2027,1,31),
    check_out=date(2027,2,12),
    adults=2, children=0,
)
print("total:", r["total"], "items:", len(r["items"]))
for i in r["items"]:
    print(" ", i["id"], i["name"][:45], "price_adult", i["price_adult"], "total", i["total_price"], "nights", i["nights"])

print()
print("--- widget destinations (is_bookable=True only) ---")
for d in search_service.destinations_for_widget():
    print(" ", d["slug"])
ctx.pop()