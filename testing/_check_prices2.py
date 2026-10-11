from datetime import date
from app import create_app
from services import search_service

app = create_app()
with app.app_context():
    r = search_service.search(
        product_type="hotel",
        destination="hurghada",
        check_in=date(2027, 1, 28),
        check_out=date(2027, 2, 4),
        adults=2,
        children=2,
    )
    priced = [i for i in r["items"] if i["total_price"] is not None][:5]
    print()
    print(f"{'NAME':<35} {'ADULT':>8} {'CHILD':>8} {'NTS':>4} {'PER NIGHT':>10} {'TOTAL':>10} CUR")
    print("-" * 95)
    for i in priced:
        print(
            f"{i['name'][:34]:<35} "
            f"{i['price_adult']:>8} "
            f"{i['price_child']:>8} "
            f"{i['nights']:>4} "
            f"{i['price_per_night']:>10} "
            f"{i['total_price']:>10} "
            f"{i['currency']}"
        )
    print()
    if priced:
        i = priced[0]
        print(f"Row: {i['name']}")
        print(f"  adult_rate   = {i['price_adult']} per night")
        print(f"  child_rate   = {i['price_child']} per night")
        print(f"  nights       = {i['nights']}")
        expected_ppn = (i['price_adult'] or 0) * 2 + (i['price_child'] or 0) * 2
        expected_tot = expected_ppn * i['nights']
        print(f"  per_night    = ({i['price_adult']} x 2) + ({i['price_child']} x 2) = {expected_ppn}")
        print(f"  total        = {expected_ppn} x {i['nights']} = {expected_tot}")
        print()
        print(f"  service returned per_night = {i['price_per_night']}  (expected {expected_ppn})")
        print(f"  service returned total     = {i['total_price']}      (expected {expected_tot})")
        print()
        ok = (
            abs((i['price_per_night'] or 0) - expected_ppn) < 0.01
            and abs((i['total_price'] or 0) - expected_tot) < 0.01
        )
        print(f"  VERDICT: {'MATCH' if ok else 'MISMATCH'}")
