import re

file_path = "blueprints/public/booking_routes.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Find the broken matching loop in booking_confirmation
old_block = '''            cards = list(db.session.scalars(select(PackageFlight).where(PackageFlight.package_id == package.id).where(PackageFlight.is_active.is_(True)).order_by(PackageFlight.sort_order, PackageFlight.id)))
            for card in cards:
                calc = compute_package_flight_card(package, card)
                if not calc.get("ok"):
                    continue
                if (booking.check_in_date and calc.get("check_in") == booking.check_in_date):
                    package_flight = card
                    break
            if package_flight is None and cards:
                package_flight = cards[0]'''

new_block = '''            cards = list(db.session.scalars(select(PackageFlight).where(PackageFlight.package_id == package.id).where(PackageFlight.is_active.is_(True)).order_by(PackageFlight.sort_order, PackageFlight.id)))
            # Match by BOTH check_in AND check_out to find the exact flight card the user selected
            for card in cards:
                calc = compute_package_flight_card(package, card)
                if not calc.get("ok"):
                    continue
                card_in = calc.get("check_in")
                card_out = calc.get("check_out")
                if (booking.check_in_date and booking.check_out_date and
                    card_in == booking.check_in_date and
                    card_out == booking.check_out_date):
                    package_flight = card
                    break
            # Fallback: match by check_in date only
            if package_flight is None and booking.check_in_date:
                for card in cards:
                    calc = compute_package_flight_card(package, card)
                    if calc.get("ok") and calc.get("check_in") == booking.check_in_date:
                        package_flight = card
                        break
            # Last resort: use the first card
            if package_flight is None and cards:
                package_flight = cards[0]'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✅ SUCCESS: Confirmation now matches flight by BOTH check_in AND check_out.")
else:
    print("❌ Could not find the exact block.")
    print("Search for 'for card in cards' in booking_routes.py manually.")
    for i, line in enumerate(content.split('\n')):
        if 'for card in cards' in line:
            print(f'Line {i+1}: {line}')
            for j in range(1, 15):
                if i+j < len(content.split('\n')):
                    print(f'Line {i+1+j}: {content.split(chr(10))[i+j]}')
            break
