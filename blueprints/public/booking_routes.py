"""
blueprints/public/booking_routes.py
───────────────────────────────────
The booking flow — the heart of the customer journey.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from sqlalchemy import select

from blueprints.public import public_bp
from extensions import db
from models import (
    Activity,
    ActivityPrice,
    Airline,
    Booking,
    Hotel,
    Package,
    PackagePrice,
    Room,
    RoomRate,
    PRODUCT_TYPE_ACTIVITY,
    PRODUCT_TYPE_HOTEL,
    PRODUCT_TYPE_PACKAGE,
    VALID_PRODUCT_TYPES,
    PackageOption,
)

from services import (
    availability_service,
    booking_service,
    payment_service,
    pricing_service,
    recommendation_service,
)


# ─── Helpers ────────────────────────────────────────────────────────
def _to_int(value, default=0, lo=0, hi=1000):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _parse_date(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d",):
        try:
            return datetime.strptime(value, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _parse_amount(value):
    if value in (None, ""):
        return Decimal("0.00")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def _parse_int_csv(value: str | None) -> list[int]:
    if not value:
        return []
    out: list[int] = []
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            out.append(int(token))
        except ValueError:
            continue
    return out


def _load_product(product_type: str, product_id: int):
    if product_type == PRODUCT_TYPE_ACTIVITY:
        return db.session.get(Activity, product_id)
    if product_type == PRODUCT_TYPE_HOTEL:
        return db.session.get(Room, product_id)
    if product_type == PRODUCT_TYPE_PACKAGE:
        return db.session.get(Package, product_id)
    return None


def _product_meta(product_type: str, product) -> dict:
    if product is None:
        return {}
    if product_type == PRODUCT_TYPE_ACTIVITY:
        price_row = db.session.scalar(
            select(ActivityPrice)
            .where(ActivityPrice.activity_id == product.id)
            .order_by(ActivityPrice.id).limit(1)
        )
        img_url = product.images[0].url if product.images else None
        if img_url and not (img_url.startswith("http") or img_url.startswith("/static")):
            img_url = "/static" + (img_url if img_url.startswith("/") else "/" + img_url)
        return {
            "name": product.name,
            "slug": product.slug,
            "image": img_url,
            "adult_price": float(price_row.adult_price) if price_row else None,
            "child_price": float(price_row.child_price) if price_row else None,
            "currency": price_row.currency if price_row else "GBP",
            "location": product.destination_id,
        }
    if product_type == PRODUCT_TYPE_HOTEL:
        hotel = db.session.get(Hotel, product.hotel_id)
        dest = None
        if hotel and hotel.destination_id:
            from models import Destination
            dest = db.session.get(Destination, hotel.destination_id)
        return {
            "name": f"{hotel.name if hotel else 'Hotel'} — {product.type}",
            "slug": hotel.slug if hotel else None,
            "image": hotel.images[0].url if hotel and hotel.images else None,
            "adult_price": float(product.base_price_per_night),
            "child_price": float(product.base_price_per_night),
            "currency": "GBP",
            "location": hotel.destination_id if hotel else None,
            "hotel": hotel.name if hotel else None,
            "room": product.type,
            "meal_plan": (product.meal_plan or "") if hasattr(product, "meal_plan") else "",
            "max_occupancy": getattr(product, "max_occupancy", None),
            "stars": hotel.stars if hotel else None,
            "address": hotel.address if hotel else None,
            "destination": dest.name if dest else None,
            "hotel_slug": hotel.slug if hotel else None,
            "room_id": product.id,
        }
    if product_type == PRODUCT_TYPE_PACKAGE:
        price_row = db.session.scalar(
            select(PackagePrice)
            .where(PackagePrice.package_id == product.id)
            .order_by(PackagePrice.id).limit(1)
        )
        dest = None
        if product.destination_id:
            from models import Destination
            dest = db.session.get(Destination, product.destination_id)
        img_url = product.images[0].url if product.images else None
        if img_url and not (img_url.startswith("http") or img_url.startswith("/static")):
            img_url = "/static" + (img_url if img_url.startswith("/") else "/" + img_url)
        return {
            "name": product.name,
            "slug": product.slug,
            "image": img_url,
            "adult_price": float(price_row.adult_price) if price_row else None,
            "child_price": float(price_row.child_price) if price_row else None,
            "currency": price_row.currency if price_row else "GBP",
            "location": product.destination_id,
            "hotel": None,
            "room": None,
            "destination": dest.name if dest else None,
        }
    return {}


def _room_stay_pricing(room: Room, check_in: date | None, check_out: date | None, adults: int, children: int) -> dict:
    nights = 1
    if check_in and check_out and check_out > check_in:
        nights = (check_out - check_in).days

    adult_rate = None
    child_rate = None
    currency = "GBP"

    if check_in is not None:
        rate = db.session.scalars(
            select(RoomRate)
            .where(RoomRate.room_id == room.id)
            .where((RoomRate.valid_from.is_(None)) | (RoomRate.valid_from <= check_in))
            .where((RoomRate.valid_to.is_(None)) | (RoomRate.valid_to >= check_in))
            .order_by(RoomRate.id.asc())
            .limit(1)
        ).first()
        if rate is not None:
            adult_rate = float(rate.adult_price or 0)
            child_rate = float(rate.child_price or 0)
            currency = rate.currency or "GBP"

    if adult_rate is None:
        adult_rate = float(room.base_price_per_night or 0)
        child_rate = 0.0

    per_night = adult_rate * adults + child_rate * children
    total = per_night * nights
    return {
        "adult_rate": adult_rate,
        "child_rate": child_rate,
        "nights": nights,
        "per_night": per_night,
        "total": total,
        "currency": currency,
    }


def _package_pricing(
    package: Package,
    adults: int,
    children: int,
    package_flight_id: int | None = None,
    check_in=None,
    check_out=None,
) -> dict:
    empty = {
        "adult_rate": None, "child_rate": None, "nights": package.duration_nights,
        "per_night": None, "per_person": None, "total": None, "currency": "GBP",
        "package_flight_id": None, "hotel_total": None, "flight_total": None,
        "markup": None, "tax": None, "transfer_fee": None, "departure_date": None,
        "return_date": None, "airline_name": None, "airline_logo": None,
        "flight_from": None, "flight_to": None, "is_land_only": False,
    }

    from services.package_options_service import options_for_package

    try:
        options = options_for_package(
            package, check_in, check_out,
            adults=adults, children=children, tolerance_days=30,
        )
    except Exception as exc:
        current_app.logger.warning("options_for_package failed: %s", exc)
        options = []

    if not options:
        return empty

    chosen = None
    # ─── FIX: Directly load the PackageFlight by ID (ignore filter) ───
    from models import PackageFlight as _PFModel
    if package_flight_id:
        pf = db.session.get(_PFModel, package_flight_id)
        if pf and pf.package_id == package.id and pf.is_active:
            # Convert the PackageFlight into an option dict
            ob = pf.outbound_flight
            ib = pf.inbound_flight
            if ob and ib:
                from services.package_pricing_service import compute_package_flight_card
                card_calc = compute_package_flight_card(package, pf)
                if card_calc.get("ok"):
                    chosen = {
                        "package_flight_id": pf.id,
                        "grand_total": card_calc.get("per_person") * max(1, adults + children),
                        "per_person": card_calc.get("per_person"),
                        "land_total": card_calc.get("hotel_total"),
                        "flight_total": card_calc.get("flight_total"),
                        "markup": card_calc.get("markup"),
                        "tax": card_calc.get("tax"),
                        "transfer_fee": card_calc.get("transfer_fee"),
                        "nights": card_calc.get("nights"),
                        "departure_date": card_calc.get("check_in"),
                        "return_date": card_calc.get("check_out"),
                        "currency": card_calc.get("currency"),
                    }

    # Fallback to the old logic only if the direct load failed
    if chosen is None and package_flight_id:
        for opt in options:
            if opt.get("package_flight_id") == package_flight_id:
                chosen = opt
                break
    if chosen is None:
        chosen = options[0] if options else None

    pax = max(1, int(adults) + int(children))
    grand_total = float(chosen.get("grand_total") or 0.0)
    if grand_total <= 0:
        per_person = float(chosen.get("per_person") or 0.0)
        grand_total = per_person * pax
    if grand_total <= 0:
        land_total = float(chosen.get("land_total") or 0.0)
        grand_total = land_total * pax
    per_person_display = (grand_total / pax) if pax > 0 else 0.0

    return {
        "adult_rate": round(per_person_display, 2),
        "child_rate": round(per_person_display, 2),
        "nights": int(chosen.get("nights") or package.duration_nights),
        "per_night": None,
        "per_person": round(per_person_display, 2),
        "total": round(grand_total, 2),
        "currency": chosen.get("currency") or "GBP",
        "package_flight_id": chosen.get("package_flight_id"),
        "hotel_total": round(float(chosen.get("land_total") or 0.0), 2),
        "flight_total": round(float(chosen.get("flight_total") or 0.0), 2),
        "markup": round(float(chosen.get("markup") or 0.0), 2),
        "tax": round(float(chosen.get("tax") or 0.0), 2),
        "transfer_fee": round(float(chosen.get("transfer_fee") or 0.0), 2),
        "departure_date": chosen.get("departure_date"),
        "return_date": chosen.get("return_date"),
        "airline_name": chosen.get("airline_name"),
        "airline_logo": chosen.get("airline_logo"),
        "flight_from": chosen.get("flight_from"),
        "flight_to": chosen.get("flight_to"),
        "is_land_only": bool(chosen.get("is_land_only")),
    }


def _activity_pricing(activity: Activity, adults: int, children: int) -> dict:
    row = db.session.scalars(
        select(ActivityPrice)
        .where(ActivityPrice.activity_id == activity.id)
        .order_by(ActivityPrice.id.asc()).limit(1)
    ).first()
    if row is None:
        return {"adult_rate": None, "child_rate": None, "nights": None, "per_night": None, "total": None, "currency": "GBP"}
    adult_rate = float(row.adult_price or 0)
    child_rate = float(row.child_price or 0)
    per_person = adult_rate * adults + child_rate * children
    return {"adult_rate": adult_rate, "child_rate": child_rate, "nights": None, "per_night": None, "per_person": per_person, "total": per_person, "currency": row.currency or "GBP"}


def _build_rooms_grouping(*, room_ids, check_in, check_out, adults, child_ages, infants):
    if not room_ids or check_in is None or check_out is None or check_out <= check_in:
        return None

    rooms: list[Room] = []
    for rid in room_ids:
        r = db.session.get(Room, rid)
        if r is None or not r.is_active:
            return None
        rooms.append(r)

    hotel_ids = {r.hotel_id for r in rooms}
    if len(hotel_ids) != 1:
        return None

    try:
        from services import hotel_pricing_service
    except Exception:
        return None

    num_rooms = len(rooms)
    nights = (check_out - check_in).days

    a_per = 2
    c_per = 1
    if num_rooms == 1:
        a_per = adults
        c_per = len(child_ages)

    per_room = [{
        "room": rooms[0],
        "adults": a_per,
        "child_ages": child_ages[:c_per],
        "infants": 0,
    }]

    priced = hotel_pricing_service.booking_pricing(
        per_room,
        check_in=check_in,
        check_out=check_out,
    )
    if not priced or not priced.get("rooms"):
        return None

    base_price = priced["rooms"][0]

    out_rooms: list[dict] = []
    for room in rooms:
        out_rooms.append({
            "room_id": room.id,
            "room_type": room.type,
            "meal_plan": room.meal_plan,
            "rate_id": base_price.get("rate_id"),
            "adults": a_per,
            "children": c_per,
            "child_ages": child_ages[:c_per],
            "infants": 0,
            "line_total": float(base_price.get("total") or 0.0),
            "currency": base_price.get("currency") or "GBP",
        })

    return {
        "rooms": out_rooms,
        "grand_total": float(base_price.get("total") or 0.0) * num_rooms,
        "currency": base_price.get("currency") or "GBP",
        "nights": nights,
        "min_rooms": num_rooms,
    }


# ─── Booking start (GET) ────────────────────────────────────────────
@public_bp.route("/booking/start/<product_type>/<int:product_id>", methods=["GET"])
def booking_start(product_type: str, product_id: int):
    if product_type not in VALID_PRODUCT_TYPES:
        abort(404)

    product = _load_product(product_type, product_id)
    if product is None:
        abort(404)

    check_in = _parse_date(request.args.get("check_in"))
    check_out = _parse_date(request.args.get("check_out"))

    # ─── FORCE FLIGHT DATES TO OVERRIDE URL DATES (in booking_start) ───
    if product_type == PRODUCT_TYPE_PACKAGE:
        raw_pfid = (request.args.get("package_flight_id") or "").strip()
        if raw_pfid and raw_pfid.lower() not in ("none", ""):
            try:
                pf_id = int(raw_pfid)
                from models import PackageFlight
                pf = db.session.get(PackageFlight, pf_id)
                if pf and pf.outbound_flight and pf.inbound_flight:
                    check_in = pf.outbound_flight.departure_date
                    check_out = pf.inbound_flight.departure_date
            except (ValueError, TypeError) as e:
                current_app.logger.warning("Flight date override in booking_start failed: %s", e)
    # ────────────────────────────────────────────────────────────────

    activity_date = _parse_date(request.args.get("date")) or _parse_date(request.args.get("activity_date"))
    adults = _to_int(request.args.get("adults"), 2, 1, 8)
    children = _to_int(request.args.get("children"), 0, 0, 8)
    infants = _to_int(request.args.get("infants"), 0, 0, 8)
    child_ages = _parse_int_csv(request.args.get("child_ages"))
    if children > 0 and len(child_ages) < children:
        child_ages = list(child_ages) + [6] * (children - len(child_ages))

    if product_type == PRODUCT_TYPE_HOTEL and not check_in:
        check_in = date.today()
        check_out = check_in + timedelta(days=7)
    elif product_type == PRODUCT_TYPE_HOTEL and check_in and not check_out:
        check_out = check_in + timedelta(days=7)
    elif product_type == PRODUCT_TYPE_PACKAGE and not activity_date:
        activity_date = date.today() + timedelta(days=30)
    elif product_type == PRODUCT_TYPE_ACTIVITY and not activity_date:
        activity_date = date.today() + timedelta(days=7)

    package_flight_id: int | None = None
    raw_pfid = (request.args.get("package_flight_id") or "").strip()
    if product_type == "package" and raw_pfid and raw_pfid.lower() != "none":
        try:
            package_flight_id = int(raw_pfid)
        except ValueError:
            package_flight_id = None

    option = None
    if product_type == "package":
        from models import PackageFlight
        if package_flight_id:
            card = db.session.get(PackageFlight, package_flight_id)
            if card and card.package_id == product.id and card.is_active:
                option = card
        if option is None:
            raw_option_id = (request.args.get("option_id") or "").strip()
            if raw_option_id and raw_option_id.lower() != "none":
                try:
                    legacy_opt_id = int(raw_option_id)
                except ValueError:
                    legacy_opt_id = None
                if legacy_opt_id:
                    candidate = db.session.get(PackageOption, legacy_opt_id)
                    if candidate and candidate.package_id == product.id and candidate.is_active:
                        option = candidate

    meta = _product_meta(product_type, product)

    if package_flight_id and option is not None:
        dep = getattr(option, "outbound_flight", None)
        if dep is not None and getattr(dep, "departure_date", None):
            meta["default_start"] = dep.departure_date.isoformat()

    rooms_grouping: dict | None = None
    rooms_json: str = ""
    rooms_param_ids = _parse_int_csv(request.args.get("rooms"))
    if product_type == PRODUCT_TYPE_HOTEL and rooms_param_ids:
        rooms_grouping = _build_rooms_grouping(
            room_ids=rooms_param_ids,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            child_ages=child_ages,
            infants=infants,
        )
        if rooms_grouping is None:
            flash("The selected rooms no longer fit this party. Showing a single-room option instead.", "warning")
        else:
            rooms_json = json.dumps([
                {
                    "room_id": r["room_id"],
                    "rate_id": r["rate_id"],
                    "adults": r["adults"],
                    "children": r["children"],
                    "child_ages": r["child_ages"],
                    "infants": r["infants"],
                }
                for r in rooms_grouping["rooms"]
            ])

    try:
        if product_type == PRODUCT_TYPE_HOTEL:
            pricing = _room_stay_pricing(product, check_in, check_out, adults, children)
        elif product_type == PRODUCT_TYPE_PACKAGE:
            pricing = _package_pricing(product, adults, children, package_flight_id=package_flight_id, check_in=check_in, check_out=check_out)
        elif product_type == PRODUCT_TYPE_ACTIVITY:
            pricing = _activity_pricing(product, adults, children)
        else:
            pricing = {}
    except Exception as exc:
        current_app.logger.warning("booking_start pricing failed: %s", exc)
        pricing = {}

    addons: list[dict] = []
    try:
        if product_type == PRODUCT_TYPE_HOTEL:
            hotel = db.session.get(Hotel, product.hotel_id)
            if hotel:
                addons = recommendation_service.recommend_addons_for_hotel(hotel.id, limit=6)
        elif product_type == PRODUCT_TYPE_PACKAGE:
            addons = recommendation_service.recommend_addons_for_package(product.id, limit=6)
    except Exception as exc:
        current_app.logger.warning("recommendations failed: %s", exc)
        addons = []

    option_summary = None
    if option is not None:
        from models import PackageFlight as _PF
        if isinstance(option, _PF):
            ob = option.outbound_flight
            airline_logo = None
            airline_name = None
            flight_from = None
            flight_to = None
            luggage = None
            if ob is not None:
                airline_name = getattr(ob, "airline", None)
                flight_from = getattr(ob, "origin", None)
                flight_to = getattr(ob, "destination", None)
                luggage = getattr(ob, "luggage_kg", None)
                if airline_name:
                    normalized = airline_name.strip().lower().replace(" ", "")
                    for a in db.session.scalars(select(Airline)):
                        if a.name and a.name.strip().lower().replace(" ", "") == normalized:
                            if a.logo_url:
                                airline_logo = a.logo_url
                            airline_name = a.name
                            break
            option_summary = {
                "id": option.id, "label": (f"{airline_name or 'Flight'} {getattr(ob, 'departure_date', '') or ''}").strip(),
                "departure_date": getattr(ob, "departure_date", None) if ob else None,
                "return_date": getattr(option.inbound_flight, "departure_date", None) if option.inbound_flight else None,
                "flight_from": flight_from, "flight_to": flight_to, "airline_name": airline_name,
                "airline_logo": airline_logo, "luggage_allowance": luggage,
                "price_adult": pricing.get("adult_rate"), "price_child": pricing.get("child_rate"), "currency": pricing.get("currency"),
            }
        else:
            flight = getattr(option, "flight", None)
            price = getattr(option, "price", None)
            airline_logo = None
            if flight is not None:
                try:
                    if getattr(flight, "airline_id", None):
                        al = db.session.get(Airline, flight.airline_id)
                        if al and al.logo_url:
                            airline_logo = al.logo_url
                    if airline_logo is None and flight.airline_name:
                        normalized = flight.airline_name.strip().lower().replace(" ", "")
                        for a in db.session.scalars(select(Airline)):
                            if a.name and a.name.strip().lower().replace(" ", "") == normalized:
                                airline_logo = a.logo_url
                                break
                except Exception:
                    airline_logo = None
            option_summary = {
                "id": option.id, "label": getattr(option, "display_label", None),
                "departure_date": getattr(option, "departure_date", None), "return_date": getattr(option, "return_date", None),
                "flight_from": getattr(flight, "flight_from", None) if flight else None,
                "flight_to": getattr(flight, "flight_to", None) if flight else None,
                "airline_name": getattr(flight, "airline_name", None) if flight else None,
                "airline_logo": airline_logo, "luggage_allowance": getattr(flight, "luggage_allowance", None) if flight else None,
                "price_adult": float(price.adult_price) if price else None, "price_child": float(price.child_price) if price else None,
                "currency": price.currency if price else None,
            }
    if rooms_grouping is not None:
        pricing_for_template = dict(pricing)
        pricing_for_template["total"] = rooms_grouping["grand_total"]
        pricing_for_template["currency"] = rooms_grouping["currency"]
        pricing_for_template["nights"] = rooms_grouping["nights"]
    else:
        pricing_for_template = pricing

    # --- NEW: Fetch detailed package room and pricing breakdown ---
       # --- NEW: Fetch detailed package room and pricing breakdown ---
    pkg_details = {}
    if product_type == PRODUCT_TYPE_PACKAGE:
        from models import Room as _RoomModel, Hotel as _HotelModel, Destination as _DestModel
        room = db.session.get(_RoomModel, product.room_id) if product.room_id else None
        hotel = db.session.get(_HotelModel, product.hotel_id) if product.hotel_id else None
        dest = db.session.get(_DestModel, product.destination_id) if product.destination_id else None
        
        pkg_details = {
            "hotel_name": hotel.name if hotel else product.name,
            "stars": hotel.stars if hotel else 0,
            "destination": dest.name if dest else "",
            "room_type": room.type if room else "",
            "meal_plan": room.meal_plan if room else "",
            "max_occupancy": room.max_occupancy if room else 0,
        }
        
        if option is not None and getattr(option, "outbound_flight", None):
            nights = (check_out - check_in).days if check_in and check_out else product.duration_nights
            land_total = 0.0
            if room:
                rate = db.session.scalars(
                    select(RoomRate)
                    .where(RoomRate.room_id == room.id)
                    .where((RoomRate.valid_from.is_(None)) | (RoomRate.valid_from <= check_in))
                    .where((RoomRate.valid_to.is_(None)) | (RoomRate.valid_to >= check_in))
                    .order_by(RoomRate.id.asc()).limit(1)
                ).first()
                rate_per_night = float(rate.adult_price) if rate else float(room.base_price_per_night or 0)
                land_total = rate_per_night * nights
            
            flight_total = 0.0
            if option.outbound_flight: flight_total += float(option.outbound_flight.price_gbp)
            if option.inbound_flight: flight_total += float(option.inbound_flight.price_gbp)
            
            from services.package_pricing_service import compute_package_flight_card
            calc = compute_package_flight_card(product, option)
            
            pkg_details.update({
                "land_cost": round(land_total, 2),
                "flight_cost": round(flight_total, 2),
                "service_fee": round(float(calc.get("markup") or 0), 2),
                "transfers": round(float(calc.get("transfer_fee") or 0), 2),
                "currency": calc.get("currency") or "GBP",
            })
    # -------------------------------------------------------------
    # -------------------------------------------------------------

    return render_template(
        "public/booking_start.html",
        product_type=product_type, product=product, meta=meta, addons=addons, option=option_summary,
        pricing=pricing_for_template, rooms_grouping=rooms_grouping, rooms_json=rooms_json,
        child_ages=child_ages, infants=infants,
        pkg_details=pkg_details,  # <--- ADD THIS LINE
        form_defaults={"check_in": check_in, "check_out": check_out, "activity_date": activity_date, "adults": adults, "children": children, "infants": infants},
    )


# ─── Booking create (POST) ──────────────────────────────────────────
@public_bp.route("/booking/create", methods=["POST"])
def booking_create():
    product_type = (request.form.get("product_type") or "").strip().lower()
    if product_type not in VALID_PRODUCT_TYPES:
        flash("Invalid product type.", "danger")
        return redirect(url_for("public.index"))

    product_id = _to_int(request.form.get("product_id"), 0, 1, 10**9)
    if product_id < 1:
        flash("Invalid product.", "danger")
        return redirect(url_for("public.index"))

    product = _load_product(product_type, product_id)
    if product is None:
        flash("This product could not be found.", "danger")
        return redirect(url_for("public.index"))

    adults = _to_int(request.form.get("adults"), 1, 1, 8)
    children = _to_int(request.form.get("children"), 0, 0, 8)
    infants = _to_int(request.form.get("infants"), 0, 0, 8)
    child_ages = _parse_int_csv(request.form.get("child_ages"))
    if children > 0 and len(child_ages) < children:
        child_ages = list(child_ages) + [6] * (children - len(child_ages))

    check_in = _parse_date(request.form.get("check_in"))
    check_out = _parse_date(request.form.get("check_out"))
    activity_date = _parse_date(request.form.get("activity_date"))

    # ─── BULLETPROOF FLIGHT DATE OVERRIDE ───
    # This MUST run AFTER all URL dates are parsed.
    # If a package_flight_id is selected, force check_in/check_out to match the flight.
    if product_type == "package":
        raw_pfid = (request.form.get("package_flight_id") or "").strip()
        if raw_pfid and raw_pfid.lower() not in ("none", ""):
            try:
                pf_id = int(raw_pfid)
                from models import PackageFlight
                pf = db.session.get(PackageFlight, pf_id)
                if pf:
                    if pf.outbound_flight and pf.outbound_flight.departure_date:
                        check_in = pf.outbound_flight.departure_date
                    if pf.inbound_flight and pf.inbound_flight.departure_date:
                        check_out = pf.inbound_flight.departure_date
            except (ValueError, TypeError) as e:
                current_app.logger.warning("Flight date override failed: %s", e)
    # ───────────────────────────────────────


    


    guest_email = (request.form.get("guest_email") or "").strip().lower()
    guest_name = (request.form.get("guest_name") or "").strip()
    guest_phone = (request.form.get("guest_phone") or "").strip()
    how_heard = (request.form.get("how_heard") or "").strip() or None
    payment_method = (request.form.get("payment_method") or "").strip() or None

    if not current_user.is_authenticated:
        if not guest_email or "@" not in guest_email:
            flash("Please provide a valid email address.", "danger")
            return redirect(request.referrer or url_for("public.index"))
        if not guest_name:
            flash("Please provide your name.", "danger")
            return redirect(request.referrer or url_for("public.index"))

    addon_specs: list[dict] = []
    for key in request.form.keys():
        if not key.startswith("addon_"):
            continue
        try:
            aid = int(key.split("_", 1)[1])
        except (ValueError, IndexError):
            continue
        qty = _to_int(request.form.get(f"addon_qty_{aid}"), 1, 1, 20)
        addon_specs.append({"activity_id": aid, "quantity": qty})

    package_flight_id: int | None = None
    if product_type == PRODUCT_TYPE_PACKAGE:
        raw_pfid = (request.form.get("package_flight_id") or "").strip()
        if raw_pfid and raw_pfid.lower() != "none":
            try:
                package_flight_id = int(raw_pfid)
            except ValueError:
                package_flight_id = None

        # Land-only check: if no card was selected, verify the package
        # can still be priced (which means it's land-only).
        if package_flight_id is None:
            _test = _package_pricing(
                product, adults, children,
                package_flight_id=None,
                check_in=check_in, check_out=check_out,
            )
            if _test.get("total") is None or _test.get("total") <= 0:
                flash("Please select a departure on the package page before booking.", "warning")
                return redirect(request.referrer or url_for("public.index"))

    rooms_selection: list[dict] | None = None
    rooms_grouping: dict | None = None
    if product_type == PRODUCT_TYPE_HOTEL:
        raw_rooms = (request.form.get("rooms") or "").strip()
        if raw_rooms:
            try:
                parsed = json.loads(raw_rooms)
            except (ValueError, TypeError):
                parsed = None
            if isinstance(parsed, list) and parsed:
                rooms_grouping = _build_rooms_grouping(
                    room_ids=[int(p.get("room_id")) for p in parsed if p.get("room_id")],
                    check_in=check_in, check_out=check_out, adults=adults, child_ages=child_ages, infants=infants,
                )
                if rooms_grouping is not None:
                    rooms_selection = [
                        {"room_id": r["room_id"], "rate_id": r["rate_id"], "adults": r["adults"], "children": r["children"],
                         "child_ages": r["child_ages"], "infants": r["infants"], "line_total": r["line_total"], "currency": r["currency"]}
                        for r in rooms_grouping["rooms"]
                    ]

    try:
        if rooms_grouping is not None:
            total = Decimal(str(rooms_grouping["grand_total"]))
        elif product_type == PRODUCT_TYPE_PACKAGE:
            # --- FIX: Use the exact same logic as the frontend ---
            pkg_pricing = _package_pricing(
                product, adults, children,
                package_flight_id=package_flight_id,
                check_in=check_in, check_out=check_out,
            )
            if pkg_pricing.get("total") is None:
                flash(pkg_pricing.get("error") or "Could not calculate package price.", "danger")
                return redirect(request.referrer or url_for("public.index"))
            total = Decimal(str(pkg_pricing["total"]))
        else:
            total = pricing_service.compute_booking_total(
                product_type=product_type, product_id=product_id, adults=adults, children=children,
                check_in=check_in, check_out=check_out, addons=addon_specs, package_flight_id=package_flight_id,
            )
    except pricing_service.PricingError as exc:
        flash(f"Pricing error: {exc}", "danger")
        return redirect(request.referrer or url_for("public.index"))

    try:
        availability = availability_service.check_availability(
            product_type=product_type, product_id=product_id, quantity=1,
            check_in=check_in, check_out=check_out, target_date=activity_date,
        )
        if not availability.available:
            flash(f"Sorry — {availability.reason}", "warning")
            return redirect(request.referrer or url_for("public.index"))
    except availability_service.AvailabilityError as exc:
        current_app.logger.warning("availability check failed: %s", exc)

    travellers: list[dict] = []
    for i in range(adults):
        raw = (request.form.get(f"traveller_name_{i}") or "").strip()
        travellers.append({"full_name": raw or guest_name or f"Adult {i + 1}", "traveller_type": "adult"})
    for j in range(children):
        idx = adults + j
        raw = (request.form.get(f"traveller_name_{idx}") or "").strip()
        travellers.append({"full_name": raw or f"Child {j + 1}", "traveller_type": "child"})
    for k in range(infants):
        idx = adults + children + k
        raw = (request.form.get(f"traveller_name_{idx}") or "").strip()
        travellers.append({"full_name": raw or f"Infant {k + 1}", "traveller_type": "infant"})

    # --- FIX: Correctly multiply addon prices by party size ---
    addon_items: list[dict] = []
    addon_total_for_booking = Decimal("0.00")
    for spec in addon_specs:
        try:
            a = db.session.get(Activity, spec["activity_id"])
            if a is None:
                continue
            price_row = db.session.scalar(select(ActivityPrice).where(ActivityPrice.activity_id == a.id).order_by(ActivityPrice.id).limit(1))
            
            # Calculate total price for this addon based on adults & children
            adult_price = Decimal(str(price_row.adult_price)) if price_row else Decimal("0.00")
            child_price = Decimal(str(price_row.child_price)) if price_row else Decimal("0.00")
            total_addon_price = (adult_price * adults) + (child_price * children)
            
            addon_total_for_booking += total_addon_price
            
        except Exception:
            total_addon_price = Decimal("0.00")
            a = None
        if a is None:
            continue
            
        # We add the line item as quantity=1, but the unit_price is the grand total of the addon
        addon_items.append({
            "product_id": a.id, 
            "quantity": 1, 
            "unit_price": float(total_addon_price), 
            "name": a.name
        })
    # ---------------------------------------------------------

    # --- ADD THE ADD-ONS TO THE FINAL BOOKING TOTAL ---
    total = total + addon_total_for_booking
    # --------------------------------------------------

    currency = "GBP"
    try:
        booking = booking_service.create_booking(
            product_type=product_type, product_id=product_id,
            travellers_adults=adults, travellers_children=children, travellers_infants=infants,
            total_amount=total, currency=currency,
            user=current_user if current_user.is_authenticated else None,
            guest_email=guest_email if not current_user.is_authenticated else None,
            guest_name=guest_name if not current_user.is_authenticated else None,
            guest_phone=guest_phone if not current_user.is_authenticated else None,
            check_in_date=check_in, check_out_date=check_out, activity_date=activity_date,
            special_requests=(request.form.get("special_requests") or "").strip() or None,
            addon_items=addon_items, how_heard=how_heard, payment_method=payment_method,
            travellers=travellers, rooms=rooms_selection,
        )
    except booking_service.BookingError as exc:
        db.session.rollback()
        flash(f"Could not create booking: {exc}", "danger")
        return redirect(request.referrer or url_for("public.index"))

    from models import Payment
    payment = db.session.scalar(select(Payment).where(Payment.booking_id == booking.id).order_by(Payment.id).limit(1))
    paypal_configured = payment_service.is_configured()

    if paypal_configured and payment is not None:
        try:
            approval_url, _ = payment_service.create_payment(payment)
            db.session.commit()
            return redirect(approval_url)
        except Exception as exc:
            current_app.logger.exception("PayPal create failed: %s", exc)
            flash("We could not reach PayPal. Your booking is saved — you will be contacted to complete payment.", "warning")
            db.session.commit()
            return redirect(url_for("public.booking_confirmation", reference=booking.reference))

    db.session.commit()
    return redirect(url_for("public.booking_confirmation", reference=booking.reference))

 
# ─── PayPal return ──────────────────────────────────────────────────
@public_bp.route("/booking/paypal/return")
def booking_paypal_return():
    payment_id = request.args.get("paymentId", "").strip()
    payer_id = request.args.get("PayerID", "").strip()

    if not payment_id or not payer_id:
        flash("Missing PayPal parameters.", "danger")
        return redirect(url_for("public.index"))

    from models import Payment
    payment = db.session.scalar(select(Payment).where(Payment.provider_payment_id == payment_id).limit(1))
    if payment is None:
        flash("We could not find that payment.", "danger")
        return redirect(url_for("public.index"))

    try:
        payment_service.execute_payment(payment, payer_id)
    except Exception as exc:
        current_app.logger.exception("PayPal execute failed: %s", exc)
        flash("Payment could not be completed.", "danger")
        db.session.commit()
        return redirect(url_for("public.index"))

    booking = db.session.get(Booking, payment.booking_id)
    try:
        if booking is not None:
            booking_service.mark_confirmed(booking, role="system")
    except Exception as exc:
        current_app.logger.warning("could not mark confirmed: %s", exc)

    db.session.commit()
    if booking is not None:
        return redirect(url_for("public.booking_confirmation", reference=booking.reference))
    return redirect(url_for("public.index"))


# ─── PayPal cancel ──────────────────────────────────────────────────
@public_bp.route("/booking/paypal/cancel")
def booking_paypal_cancel():
    flash("Payment was cancelled. Your booking is still pending.", "warning")
    return redirect(url_for("public.index"))


# ─── Confirmation ───────────────────────────────────────────────────
@public_bp.route("/booking/confirmation/<reference>")
def booking_confirmation(reference: str):
    booking = db.session.scalar(select(Booking).where(Booking.reference == reference))
    if booking is None:
        abort(404)

    from models import (
        BookingItem, Package, PackageFlight, Hotel, Room, Destination,
        PackageImage, PackageInclusion, PackageExclusion, PackageItinerary,
        PackageTip, FlightPrice,
    )
    from services.package_pricing_service import compute_package_flight_card

    items = list(db.session.scalars(select(BookingItem).where(BookingItem.booking_id == booking.id).order_by(BookingItem.id)))
    primary_item = next((it for it in items if it.item_type == "primary"), items[0] if items else None)
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
            destination = db.session.get(Destination, package.destination_id) if package.destination_id else None
            images = list(db.session.scalars(select(PackageImage).where(PackageImage.package_id == package.id).order_by(PackageImage.sort_order)))
            inclusions = list(db.session.scalars(select(PackageInclusion).where(PackageInclusion.package_id == package.id).order_by(PackageInclusion.sort_order)))
            exclusions = list(db.session.scalars(select(PackageExclusion).where(PackageExclusion.package_id == package.id).order_by(PackageExclusion.sort_order)))
            itineraries = list(db.session.scalars(select(PackageItinerary).where(PackageItinerary.package_id == package.id).order_by(PackageItinerary.day_number)))
            tips = list(db.session.scalars(select(PackageTip).where(PackageTip.package_id == package.id).order_by(PackageTip.sort_order, PackageTip.id)))

            cards = list(db.session.scalars(select(PackageFlight).where(PackageFlight.package_id == package.id).where(PackageFlight.is_active.is_(True)).order_by(PackageFlight.sort_order, PackageFlight.id)))
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
                package_flight = cards[0]

            if package_flight is not None:
                flight_out = package_flight.outbound_flight
                flight_back = package_flight.inbound_flight
                calc = compute_package_flight_card(package, package_flight)
                if calc.get("ok"):
                    per_person = float(calc.get("per_person") or 0)
                    pax = max(1, (booking.travellers_adults or 1) + (booking.travellers_children or 0))
                    pricing_breakdown = {
                        "per_person": round(per_person, 2), "pax": pax, "land_total": round(float(calc.get("hotel_total") or 0), 2),
                        "flight_total": round(float(calc.get("flight_total") or 0), 2), "markup": round(float(calc.get("markup") or 0), 2),
                        "tax": round(float(calc.get("tax") or 0), 2), "transfer": round(float(calc.get("transfer_fee") or 0), 2),
                        "subtotal": round(per_person * pax, 2), "currency": calc.get("currency") or booking.currency or "GBP", "nights": int(calc.get("nights") or 0),
                    }

    from decimal import Decimal as _Dec
    addon_total = sum((_Dec(str(it.line_total or 0)) for it in addon_items), _Dec("0.00"))

    hotel_obj = None
    hotel_rooms = []
    hotel_images = []
    hotel_facilities = []

    activity_obj = None
    activity_images = []
    activity_inclusions = []
    activity_tips = []
    activity_languages = []
    activity_price_row = None

    hotel_room_obj = None
    booking_rooms_detail: list[dict] = []
    if booking.product_type == "hotel" and primary_item is not None:
        from models import Room as _RoomLookup, BookingRoom as _BR
        hotel_room_obj = db.session.get(_RoomLookup, primary_item.product_id)
        hotel_obj = db.session.get(Hotel, hotel_room_obj.hotel_id) if hotel_room_obj is not None else None
        if hotel_obj is not None:
            from models import HotelImage, HotelFacility, Room as _Room
            hotel_images = list(db.session.scalars(select(HotelImage).where(HotelImage.hotel_id == hotel_obj.id).order_by(HotelImage.sort_order)))
            hotel_facilities = list(db.session.scalars(select(HotelFacility).where(HotelFacility.hotel_id == hotel_obj.id).order_by(HotelFacility.id).limit(8)))
            hotel_rooms = [hotel_room_obj] if hotel_room_obj is not None else []
            if destination is None and hotel_obj.destination_id:
                destination = db.session.get(Destination, hotel_obj.destination_id)
            if not images and hotel_images:
                images = hotel_images

        for br in db.session.scalars(select(_BR).where(_BR.booking_id == booking.id).order_by(_BR.room_index)):
            br_room = db.session.get(Room, br.room_id)
            booking_rooms_detail.append({
                "room": br_room, "room_index": br.room_index, "adults": br.adults, "children": br.children,
                "infants": br.infants, "child_ages": br.child_ages or [], "line_total": br.line_total, "currency": br.currency,
            })

    if booking.product_type == "activity" and primary_item is not None:
        activity_obj = db.session.get(Activity, primary_item.product_id)
        if activity_obj is not None:
            from models import ActivityImage, ActivityInclusion, ActivityTip, ActivityLanguage, ActivityPrice
            activity_images = list(db.session.scalars(select(ActivityImage).where(ActivityImage.activity_id == activity_obj.id).order_by(ActivityImage.sort_order)))
            activity_inclusions = list(db.session.scalars(select(ActivityInclusion).where(ActivityInclusion.activity_id == activity_obj.id).order_by(ActivityInclusion.sort_order)))
            activity_tips = list(db.session.scalars(select(ActivityTip).where(ActivityTip.activity_id == activity_obj.id).order_by(ActivityTip.sort_order)))
            activity_languages = list(db.session.scalars(select(ActivityLanguage).where(ActivityLanguage.activity_id == activity_obj.id)))
            activity_price_row = db.session.scalar(select(ActivityPrice).where(ActivityPrice.activity_id == activity_obj.id).order_by(ActivityPrice.id).limit(1))
            if destination is None and activity_obj.destination_id:
                destination = db.session.get(Destination, activity_obj.destination_id)
            if not images and activity_images:
                images = activity_images

    return render_template(
        "public/booking_confirmation.html", booking=booking, payment_service_configured=payment_service.is_configured(),
        primary_item=primary_item, hotel_obj=hotel_obj, hotel_room_obj=hotel_room_obj, hotel_rooms=hotel_rooms,
        hotel_images=hotel_images, hotel_facilities=hotel_facilities, booking_rooms_detail=booking_rooms_detail,
        activity_obj=activity_obj, activity_images=activity_images, activity_inclusions=activity_inclusions,
        activity_tips=activity_tips, activity_languages=activity_languages, activity_price_row=activity_price_row,
        addon_items=addon_items, addon_total=round(addon_total, 2), package=package, package_flight=package_flight,
        flight_out=flight_out, flight_back=flight_back, hotel=hotel, room=room, destination=destination, images=images,
        inclusions=inclusions, exclusions=exclusions, itineraries=itineraries, tips=tips, pricing_breakdown=pricing_breakdown,
    )