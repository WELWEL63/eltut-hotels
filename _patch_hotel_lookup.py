path = "blueprints/public/booking_routes.py"
s = open(path, "r", encoding="utf-8").read()

old = '''    if booking.product_type == "hotel" and primary_item is not None:
        # primary_item.product_id is the Hotel id in the hotel booking flow
        hotel_obj = db.session.get(Hotel, primary_item.product_id)
        if hotel_obj is not None:'''

new = '''    hotel_room_obj = None
    if booking.product_type == "hotel" and primary_item is not None:
        # Hotel bookings store primary_item.product_id = Room.id.
        # Resolve Room -> Hotel.
        from models import Room as _RoomLookup
        hotel_room_obj = db.session.get(_RoomLookup, primary_item.product_id)
        hotel_obj = (
            db.session.get(Hotel, hotel_room_obj.hotel_id)
            if hotel_room_obj is not None else None
        )
        if hotel_obj is not None:'''

assert old in s, "hotel branch header not found"
s = s.replace(old, new, 1)

old_rooms = '''            hotel_rooms = list(db.session.scalars(
                select(_Room)
                .where(_Room.hotel_id == hotel_obj.id)
                .where(_Room.is_active.is_(True))
                .order_by(_Room.base_price_per_night.asc().nulls_last())
            ))'''
new_rooms = '''            # Only show the booked room, not the whole list
            hotel_rooms = [hotel_room_obj] if hotel_room_obj is not None else []'''
if old_rooms in s:
    s = s.replace(old_rooms, new_rooms, 1)
    print("room list trimmed to booked room")

# Pass hotel_room_obj through to the template
old_pass = "        hotel_obj=hotel_obj,\n        hotel_rooms=hotel_rooms,"
new_pass = "        hotel_obj=hotel_obj,\n        hotel_room_obj=hotel_room_obj,\n        hotel_rooms=hotel_rooms,"
if old_pass in s:
    s = s.replace(old_pass, new_pass, 1)
    print("hotel_room_obj passed to template")

open(path, "w", encoding="utf-8").write(s)
print("booking_confirmation route patched")