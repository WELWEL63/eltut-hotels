from datetime import date
from app import create_app
from services import search_service

app = create_app()
with app.app_context():
    r = search_service.search(
        product_type="hotel",
        destination="hurghada",
        check_in=date(2027, 1, 20),
        check_out=date(2027, 1, 27),
        adults=2,
        children=2,
    )
    priced = [i for i in r["items"] if i["total_price"] is not None][:5]
    print()
    print(f"{'NAME':<35} {'ADULT':>8} {'CHILD':>8} {'NIGHTS':>7} {'PER NIGHT':>10} {'TOTAL':>10} CUR")
    print("-" * 100)
    for i in priced:
        print(
            f"{i['name'][:34]:<35} "
            f"{i['price_adult']:>8} "
            f"{i['price_child']:>8} "
            f"{i['nights']:>7} "
            f"{i['price_per_night']:>10} "
            f"{i['total_price']:>10} "
            f"{i['currency']}"
        )
    print()
    if priced:
        i = priced[0]
        print(f"VERIFY: {i['price_adult']} x 2 + {i['price_child']} x 2 = "
              f"{(i['price_adult'] or 0) * 2 + (i['price_child'] or 0) * 2}")
        print(f"VERIFY: per_night {i['price_per_night']} x {i['nights']} nights = "
              f"{(i['price_per_night'] or 0) * i['nights']}")
        print(f"VERIFY: total_price = {i['total_price']}")
