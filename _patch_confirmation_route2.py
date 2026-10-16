path = "blueprints/public/booking_routes.py"
s = open(path, "r", encoding="utf-8").read()

# Fix Decimal/float mixing
old = '''    # Addon subtotal
    addon_total = sum(
        (float(it.line_total or 0) for it in addon_items),
        0.0,
    )'''
new = '''    # Addon subtotal — Decimal to avoid float/Decimal mixing in templates
    from decimal import Decimal as _Dec
    addon_total = sum(
        (_Dec(str(it.line_total or 0)) for it in addon_items),
        _Dec("0.00"),
    )'''
assert old in s, "addon_total block not found"
s = s.replace(old, new, 1)

# Add hotel + activity enrich branches. Insert just before the
# "return render_template(" that follows the enrich block.
anchor = '''    return render_template(
        "public/booking_confirmation.html",
        booking=booking,
        payment_service_configured=payment_service.is_configured(),
        primary_item=primary_item,'''

hotel_activity_block = '''    hotel_obj = None
    hotel_rooms = []
    hotel_images = []
    hotel_facilities = []

    activity_obj = None
    activity_images = []
    activity_inclusions = []
    activity_tips = []
    activity_languages = []
    activity_price_row = None

    if booking.product_type == "hotel" and primary_item is not None:
        # primary_item.product_id is the Hotel id in the hotel booking flow
        hotel_obj = db.session.get(Hotel, primary_item.product_id)
        if hotel_obj is not None:
            from models import HotelImage, HotelFacility, Room as _Room
            hotel_images = list(db.session.scalars(
                select(HotelImage)
                .where(HotelImage.hotel_id == hotel_obj.id)
                .order_by(HotelImage.sort_order)
            ))
            hotel_facilities = list(db.session.scalars(
                select(HotelFacility)
                .where(HotelFacility.hotel_id == hotel_obj.id)
                .order_by(HotelFacility.id)
                .limit(8)
            ))
            hotel_rooms = list(db.session.scalars(
                select(_Room)
                .where(_Room.hotel_id == hotel_obj.id)
                .where(_Room.is_active.is_(True))
                .order_by(_Room.base_price_per_night.asc().nulls_last())
            ))
            if destination is None and hotel_obj.destination_id:
                destination = db.session.get(Destination, hotel_obj.destination_id)
            if not images and hotel_images:
                images = hotel_images

    if booking.product_type == "activity" and primary_item is not None:
        activity_obj = db.session.get(Activity, primary_item.product_id)
        if activity_obj is not None:
            from models import ActivityImage, ActivityInclusion, ActivityTip, ActivityLanguage, ActivityPrice
            activity_images = list(db.session.scalars(
                select(ActivityImage)
                .where(ActivityImage.activity_id == activity_obj.id)
                .order_by(ActivityImage.sort_order)
            ))
            activity_inclusions = list(db.session.scalars(
                select(ActivityInclusion)
                .where(ActivityInclusion.activity_id == activity_obj.id)
                .order_by(ActivityInclusion.sort_order)
            ))
            activity_tips = list(db.session.scalars(
                select(ActivityTip)
                .where(ActivityTip.activity_id == activity_obj.id)
                .order_by(ActivityTip.sort_order)
            ))
            activity_languages = list(db.session.scalars(
                select(ActivityLanguage)
                .where(ActivityLanguage.activity_id == activity_obj.id)
            ))
            activity_price_row = db.session.scalar(
                select(ActivityPrice)
                .where(ActivityPrice.activity_id == activity_obj.id)
                .order_by(ActivityPrice.id)
                .limit(1)
            )
            if destination is None and activity_obj.destination_id:
                destination = db.session.get(Destination, activity_obj.destination_id)
            if not images and activity_images:
                images = activity_images

    return render_template(
        "public/booking_confirmation.html",
        booking=booking,
        payment_service_configured=payment_service.is_configured(),
        primary_item=primary_item,
        hotel_obj=hotel_obj,
        hotel_rooms=hotel_rooms,
        hotel_images=hotel_images,
        hotel_facilities=hotel_facilities,
        activity_obj=activity_obj,
        activity_images=activity_images,
        activity_inclusions=activity_inclusions,
        activity_tips=activity_tips,
        activity_languages=activity_languages,
        activity_price_row=activity_price_row,'''

assert anchor in s, "return render_template anchor not found"
s = s.replace(anchor, hotel_activity_block, 1)

open(path, "w", encoding="utf-8").write(s)
print("booking_confirmation route extended")