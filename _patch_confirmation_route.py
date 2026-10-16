path = "blueprints/public/booking_routes.py"
s = open(path, "r", encoding="utf-8").read()

old = '''@public_bp.route("/booking/confirmation/<reference>")
def booking_confirmation(reference: str):
    """Post-booking confirmation page."""
    booking = db.session.scalar(
        select(Booking).where(Booking.reference == reference)
    )
    if booking is None:
        abort(404)
    return render_template(
        "public/booking_confirmation.html",
        booking=booking,
        payment_service_configured=payment_service.is_configured(),
    )'''

new = '''@public_bp.route("/booking/confirmation/<reference>")
def booking_confirmation(reference: str):
    """Post-booking confirmation page."""
    booking = db.session.scalar(
        select(Booking).where(Booking.reference == reference)
    )
    if booking is None:
        abort(404)

    # ─── Enrich context for the rich confirmation page ─────────────
    from models import (
        BookingItem, Package, PackageFlight, Hotel, Room, Destination,
        PackageImage, PackageInclusion, PackageExclusion, PackageItinerary,
        PackageTip, FlightPrice,
    )
    from services.package_pricing_service import compute_package_flight_card

    items = list(db.session.scalars(
        select(BookingItem)
        .where(BookingItem.booking_id == booking.id)
        .order_by(BookingItem.id)
    ))

    primary_item = next(
        (it for it in items if it.item_type == "primary"),
        items[0] if items else None,
    )
    addon_items = [it for it in items if it.item_type != "primary"]

    package = None
    package_flight = None
    hotel = None
    room = None
    destination = None
    images = []
    inclusions = []
    exclusions = []
    itineraries = []
    tips = []
    pricing_breakdown = None
    flight_out = None
    flight_back = None

    if booking.product_type == "package" and primary_item is not None:
        package = db.session.get(Package, primary_item.product_id)
        if package is not None:
            hotel = db.session.get(Hotel, package.hotel_id) if package.hotel_id else None
            room = db.session.get(Room, package.room_id) if package.room_id else None
            destination = (
                db.session.get(Destination, package.destination_id)
                if package.destination_id else None
            )
            images = list(db.session.scalars(
                select(PackageImage)
                .where(PackageImage.package_id == package.id)
                .order_by(PackageImage.sort_order)
            ))
            inclusions = list(db.session.scalars(
                select(PackageInclusion)
                .where(PackageInclusion.package_id == package.id)
                .order_by(PackageInclusion.sort_order)
            ))
            exclusions = list(db.session.scalars(
                select(PackageExclusion)
                .where(PackageExclusion.package_id == package.id)
                .order_by(PackageExclusion.sort_order)
            ))
            itineraries = list(db.session.scalars(
                select(PackageItinerary)
                .where(PackageItinerary.package_id == package.id)
                .order_by(PackageItinerary.day_number)
            ))
            tips = list(db.session.scalars(
                select(PackageTip)
                .where(PackageTip.package_id == package.id)
                .order_by(PackageTip.sort_order, PackageTip.id)
            ))

            # The card the customer picked — infer the cheapest matching one
            # for the booking dates if we can't know for sure.
            cards = list(db.session.scalars(
                select(PackageFlight)
                .where(PackageFlight.package_id == package.id)
                .where(PackageFlight.is_active.is_(True))
                .order_by(PackageFlight.sort_order, PackageFlight.id)
            ))
            for card in cards:
                calc = compute_package_flight_card(package, card)
                if not calc.get("ok"):
                    continue
                if (booking.check_in_date and calc.get("check_in") == booking.check_in_date):
                    package_flight = card
                    break
            if package_flight is None and cards:
                package_flight = cards[0]

            if package_flight is not None:
                flight_out = package_flight.outbound_flight
                flight_back = package_flight.inbound_flight
                calc = compute_package_flight_card(package, package_flight)
                if calc.get("ok"):
                    per_person = float(calc.get("per_person") or 0)
                    pax = max(1, (booking.travellers_adults or 1) + (booking.travellers_children or 0))
                    pricing_breakdown = {
                        "per_person": round(per_person, 2),
                        "pax": pax,
                        "land_total": round(float(calc.get("hotel_total") or 0), 2),
                        "flight_total": round(float(calc.get("flight_total") or 0), 2),
                        "markup": round(float(calc.get("markup") or 0), 2),
                        "tax": round(float(calc.get("tax") or 0), 2),
                        "transfer": round(float(calc.get("transfer_fee") or 0), 2),
                        "subtotal": round(per_person * pax, 2),
                        "currency": calc.get("currency") or booking.currency or "GBP",
                        "nights": int(calc.get("nights") or 0),
                    }

    # Addon subtotal
    addon_total = sum(
        (float(it.line_total or 0) for it in addon_items),
        0.0,
    )

    return render_template(
        "public/booking_confirmation.html",
        booking=booking,
        payment_service_configured=payment_service.is_configured(),
        primary_item=primary_item,
        addon_items=addon_items,
        addon_total=round(addon_total, 2),
        package=package,
        package_flight=package_flight,
        flight_out=flight_out,
        flight_back=flight_back,
        hotel=hotel,
        room=room,
        destination=destination,
        images=images,
        inclusions=inclusions,
        exclusions=exclusions,
        itineraries=itineraries,
        tips=tips,
        pricing_breakdown=pricing_breakdown,
    )'''

assert old in s, "confirmation route marker not found"
s = s.replace(old, new, 1)
open(path, "w", encoding="utf-8").write(s)
print("booking_confirmation route enriched")