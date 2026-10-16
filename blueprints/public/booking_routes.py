"""
blueprints/public/booking_routes.py
───────────────────────────────────
The booking flow — the heart of the customer journey.

ROUTES
    GET  /booking/start/<product_type>/<int:product_id>    booking form
    POST /booking/create                                   create booking + redirect to PayPal
    GET  /booking/paypal/return                            PayPal return URL
    GET  /booking/paypal/cancel                            PayPal cancel URL
    GET  /booking/confirmation/<reference>                 success page

DESIGN NOTES
    - Works for GUEST and LOGGED-IN customers. Logged-in users get their
      name/email/phone pre-filled on the form.
    - One flow handles all three product types (activity | hotel | package).
    - The booking_start page READS its defaults from the URL query string:
        hotel:     ?check_in=...&check_out=...&adults=...&children=...
        package:   ?check_in=...&check_out=...&adults=...&children=...&option_id=...
        activity:  ?date=...&adults=...&children=...
      So a "Book now" link from a detail page lands with everything filled.
    - The page also COMPUTES the price for the stay up-front so the user
      sees the total before submitting.
    - Add-on upsells come from services.recommendation_service and are
      shown on the form; ticked ones become booking_items.
    - Prices and availability are ALWAYS recomputed server-side — the
      browser is never trusted.
    - The 5-table create happens inside services.booking_service.
    - Payment: if PayPal is configured we redirect to the approval URL;
      otherwise we go straight to the confirmation page so the whole
      flow is demoable without real PayPal credentials.
"""

from __future__ import annotations

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


def _load_product(product_type: str, product_id: int):
    """Return the ORM object for the given product, or None."""
    if product_type == PRODUCT_TYPE_ACTIVITY:
        return db.session.get(Activity, product_id)
    if product_type == PRODUCT_TYPE_HOTEL:
        return db.session.get(Room, product_id)   # room is the bookable unit
    if product_type == PRODUCT_TYPE_PACKAGE:
        return db.session.get(Package, product_id)
    return None


def _product_meta(product_type: str, product) -> dict:
    """Small dict used by the template — name, price, image."""
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
            from models import Destination  # noqa: PLC0415
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
            from models import Destination  # noqa: PLC0415
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


def _room_stay_pricing(room: Room, check_in: date | None, check_out: date | None,
                       adults: int, children: int) -> dict:
    """Per-night + total for a hotel room for the specific stay."""
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
) -> dict:
    """Price a package booking from a selected PackageFlight card.

    Prices the card via services.package_pricing_service, the same
    function the admin preview uses. No card -> zeroed dict so the
    caller shows "select a departure" instead of a wrong number.
    """
    from services.package_pricing_service import compute_package_flight_card

    empty = {
        "adult_rate": None, "child_rate": None, "nights": package.duration_nights,
        "per_night": None, "per_person": None, "total": None, "currency": "GBP",
        "package_flight_id": None,
        "hotel_total": None, "flight_total": None, "markup": None, "tax": None,
        "transfer_fee": None,
        "departure_date": None, "return_date": None,
        "airline_name": None, "airline_logo": None,
        "flight_from": None, "flight_to": None,
    }
    if not package_flight_id:
        return empty

    from models import PackageFlight
    card = db.session.get(PackageFlight, package_flight_id)
    if card is None or card.package_id != package.id or not card.is_active:
        return empty

    calc = compute_package_flight_card(package, card)
    if not calc.get("ok"):
        return empty

    pax = max(1, int(adults) + int(children))
    per_person = float(calc.get("per_person") or 0.0)
    grand_total = per_person * pax

    return {
        "adult_rate": round(per_person, 2),
        "child_rate": round(per_person, 2),
        "nights": int(calc.get("nights") or package.duration_nights),
        "per_night": None,
        "per_person": round(per_person, 2),
        "total": round(grand_total, 2),
        "currency": calc.get("currency") or "GBP",
        "package_flight_id": card.id,
        "hotel_total": round(float(calc.get("hotel_total") or 0.0), 2),
        "flight_total": round(float(calc.get("flight_total") or 0.0), 2),
        "markup": round(float(calc.get("markup") or 0.0), 2),
        "tax": round(float(calc.get("tax") or 0.0), 2),
        "transfer_fee": round(float(calc.get("transfer_fee") or 0.0), 2),
        "departure_date": calc.get("check_in"),
        "return_date": calc.get("check_out"),
        "airline_name": calc.get("airline_name"),
        "airline_logo": calc.get("airline_logo"),
        "flight_from": calc.get("flight_from"),
        "flight_to": calc.get("flight_to"),
    }




def _activity_pricing(activity: Activity, adults: int, children: int) -> dict:
    row = db.session.scalars(
        select(ActivityPrice)
        .where(ActivityPrice.activity_id == activity.id)
        .order_by(ActivityPrice.id.asc()).limit(1)
    ).first()
    if row is None:
        return {
            "adult_rate": None, "child_rate": None, "nights": None,
            "per_night": None, "total": None, "currency": "GBP",
        }
    adult_rate = float(row.adult_price or 0)
    child_rate = float(row.child_price or 0)
    per_person = adult_rate * adults + child_rate * children
    return {
        "adult_rate": adult_rate,
        "child_rate": child_rate,
        "nights": None,
        "per_night": None,
        "per_person": per_person,
        "total": per_person,
        "currency": row.currency or "GBP",
    }


# ─── Booking start (GET) ────────────────────────────────────────────
@public_bp.route("/booking/start/<product_type>/<int:product_id>", methods=["GET"])
def booking_start(product_type: str, product_id: int):
    """Show the booking form for a product.

    Reads defaults from the URL query string so a "Book now" link from a
    detail page lands with everything pre-filled.
    """
    if product_type not in VALID_PRODUCT_TYPES:
        abort(404)

    product = _load_product(product_type, product_id)
    if product is None:
        abort(404)

    # ─── Read defaults from URL ────────────────────────────────────
    check_in = _parse_date(request.args.get("check_in"))
    check_out = _parse_date(request.args.get("check_out"))
    activity_date = _parse_date(request.args.get("date")) or _parse_date(request.args.get("activity_date"))
    adults = _to_int(request.args.get("adults"), 2, 1, 8)
    children = _to_int(request.args.get("children"), 0, 0, 8)

    # Sensible fallbacks
    if product_type == PRODUCT_TYPE_HOTEL and not check_in:
        check_in = date.today()
        check_out = check_in + timedelta(days=7)
    elif product_type == PRODUCT_TYPE_HOTEL and check_in and not check_out:
        check_out = check_in + timedelta(days=7)
    elif product_type == PRODUCT_TYPE_PACKAGE and not activity_date:
        activity_date = date.today() + timedelta(days=30)
    elif product_type == PRODUCT_TYPE_ACTIVITY and not activity_date:
        activity_date = date.today() + timedelta(days=7)

    # ─── Optional departure card (packages only) ───────────────────
    # The detail page sends ?package_flight_id=<PackageFlight.id>.
    # Legacy ?option_id=<PackageOption.id> is still accepted as a
    # fallback so old bookmarked URLs don't 404.
    package_flight_id: int | None = None
    raw_pfid = (request.args.get("package_flight_id") or "").strip()
    if product_type == "package" and raw_pfid:
        try:
            package_flight_id = int(raw_pfid)
        except ValueError:
            package_flight_id = None

    option = None  # kept for template backward-compat
    if product_type == "package":
        from models import PackageFlight
        if package_flight_id:
            card = db.session.get(PackageFlight, package_flight_id)
            if card and card.package_id == product.id and card.is_active:
                option = card
        if option is None:
            raw_option_id = (request.args.get("option_id") or "").strip()
            if raw_option_id:
                try:
                    legacy_opt_id = int(raw_option_id)
                except ValueError:
                    legacy_opt_id = None
                if legacy_opt_id:
                    candidate = db.session.get(PackageOption, legacy_opt_id)
                    if candidate and candidate.package_id == product.id and candidate.is_active:
                        option = candidate

    meta = _product_meta(product_type, product)

    # If a departure card was selected, seed meta's display fields.
    # The authoritative price comes from _package_pricing() below.
    if package_flight_id and option is not None:
        dep = getattr(option, "outbound_flight", None)
        if dep is not None and getattr(dep, "departure_date", None):
            meta["default_start"] = dep.departure_date.isoformat()


    # ─── Compute the price for the stay (server-side) ──────────────
    try:
        if product_type == PRODUCT_TYPE_HOTEL:
            pricing = _room_stay_pricing(product, check_in, check_out, adults, children)
        elif product_type == PRODUCT_TYPE_PACKAGE:
            pricing = _package_pricing(
                product, adults, children,
                package_flight_id=package_flight_id,
            )
        elif product_type == PRODUCT_TYPE_ACTIVITY:
            pricing = _activity_pricing(product, adults, children)
        else:
            pricing = {}
    except Exception as exc:
        current_app.logger.warning("booking_start pricing failed: %s", exc)
        pricing = {}

    # ─── Recommended add-ons (upsell) ──────────────────────────────
    addons: list[dict] = []
    try:
        if product_type == PRODUCT_TYPE_ACTIVITY:
            pass
        elif product_type == PRODUCT_TYPE_HOTEL:
            hotel = db.session.get(Hotel, product.hotel_id)
            if hotel:
                addons = recommendation_service.recommend_addons_for_hotel(
                    hotel.id, limit=6
                )
        elif product_type == PRODUCT_TYPE_PACKAGE:
            addons = recommendation_service.recommend_addons_for_package(
                product.id, limit=6
            )
    except Exception as exc:
        current_app.logger.warning("recommendations failed: %s", exc)
        addons = []

    # ─── Serialise the option for the template ─────────────────────
    option_summary = None
    if option is not None:
        from models import PackageFlight as _PF
        if isinstance(option, _PF):
            # PackageFlight card — pull display fields from outbound leg
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
                "id": option.id,
                "label": (
                    f"{airline_name or 'Flight'} "
                    f"{getattr(ob, 'departure_date', '') or ''}"
                ).strip(),
                "departure_date": getattr(ob, "departure_date", None) if ob else None,
                "return_date": (
                    getattr(option.inbound_flight, "departure_date", None)
                    if option.inbound_flight else None
                ),
                "flight_from": flight_from,
                "flight_to": flight_to,
                "airline_name": airline_name,
                "airline_logo": airline_logo,
                "luggage_allowance": luggage,
                "price_adult": pricing.get("adult_rate"),
                "price_child": pricing.get("child_rate"),
                "currency": pricing.get("currency"),
            }
        else:
            # Legacy PackageOption
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
                "id": option.id,
                "label": getattr(option, "display_label", None),
                "departure_date": getattr(option, "departure_date", None),
                "return_date": getattr(option, "return_date", None),
                "flight_from": getattr(flight, "flight_from", None) if flight else None,
                "flight_to": getattr(flight, "flight_to", None) if flight else None,
                "airline_name": getattr(flight, "airline_name", None) if flight else None,
                "airline_logo": airline_logo,
                "luggage_allowance": getattr(flight, "luggage_allowance", None) if flight else None,
                "price_adult": float(price.adult_price) if price else None,
                "price_child": float(price.child_price) if price else None,
                "currency": price.currency if price else None,
            }

    return render_template(
        "public/booking_start.html",
        product_type=product_type,
        product=product,
        meta=meta,
        addons=addons,
        option=option_summary,
        pricing=pricing,
        form_defaults={
            "check_in": check_in,
            "check_out": check_out,
            "activity_date": activity_date,
            "adults": adults,
            "children": children,
        },
    )


# ─── Booking create (POST) ──────────────────────────────────────────
@public_bp.route("/booking/create", methods=["POST"])
def booking_create():
    """Create the booking, then either redirect to PayPal or confirm."""
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

    # Travellers
    adults = _to_int(request.form.get("adults"), 1, 1, 8)
    children = _to_int(request.form.get("children"), 0, 0, 8)

    # Dates
    check_in = _parse_date(request.form.get("check_in"))
    check_out = _parse_date(request.form.get("check_out"))
    activity_date = _parse_date(request.form.get("activity_date"))

    # Guest details
    guest_email = (request.form.get("guest_email") or "").strip().lower()
    guest_name = (request.form.get("guest_name") or "").strip()
    guest_phone = (request.form.get("guest_phone") or "").strip()

    # Marketing + payment preferences
    how_heard = (request.form.get("how_heard") or "").strip() or None
    payment_method = (request.form.get("payment_method") or "").strip() or None

    if not current_user.is_authenticated:
        if not guest_email or "@" not in guest_email:
            flash("Please provide a valid email address.", "danger")
            return redirect(request.referrer or url_for("public.index"))
        if not guest_name:
            flash("Please provide your name.", "danger")
            return redirect(request.referrer or url_for("public.index"))

    # Add-ons from the form
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
    # Package flight card (packages only) — the single source of
    # truth for package pricing. Missing for hotels/activities.
    package_flight_id: int | None = None
    if product_type == PRODUCT_TYPE_PACKAGE:
        raw_pfid = (request.form.get("package_flight_id") or "").strip()
        if raw_pfid:
            try:
                package_flight_id = int(raw_pfid)
            except ValueError:
                package_flight_id = None
        if package_flight_id is None:
            flash(
                "Please select a departure on the package page before booking.",
                "warning",
            )
            return redirect(request.referrer or url_for("public.index"))

    # Compute the total server-side from the same source the form shows.
    try:
        total = pricing_service.compute_booking_total(
            product_type=product_type,
            product_id=product_id,
            adults=adults,
            children=children,
            check_in=check_in,
            check_out=check_out,
            addons=addon_specs,
            package_flight_id=package_flight_id,
        )
    except pricing_service.PricingError as exc:
        flash(f"Pricing error: {exc}", "danger")
        return redirect(request.referrer or url_for("public.index"))

    # Availability check
    try:
        availability = availability_service.check_availability(
            product_type=product_type,
            product_id=product_id,
            quantity=1,
            check_in=check_in,
            check_out=check_out,
            target_date=activity_date,
        )
        if not availability.available:
            flash(f"Sorry — {availability.reason}", "warning")
            return redirect(request.referrer or url_for("public.index"))
    except availability_service.AvailabilityError as exc:
        current_app.logger.warning("availability check failed: %s", exc)

    # Travellers — named per person if provided, else fallback to guest name
    travellers: list[dict] = []
    for i in range(adults):
        raw = (request.form.get(f"traveller_name_{i}") or "").strip()
        travellers.append({
            "full_name": raw or guest_name or f"Adult {i + 1}",
            "traveller_type": "adult",
        })
    for j in range(children):
        idx = adults + j
        raw = (request.form.get(f"traveller_name_{idx}") or "").strip()
        travellers.append({
            "full_name": raw or f"Child {j + 1}",
            "traveller_type": "child",
        })

    # Add-on items
    addon_items: list[dict] = []
    for spec in addon_specs:
        try:
            a = db.session.get(Activity, spec["activity_id"])
            if a is None:
                continue
            price_row = db.session.scalar(
                select(ActivityPrice)
                .where(ActivityPrice.activity_id == a.id)
                .order_by(ActivityPrice.id).limit(1)
            )
            unit = float(price_row.adult_price) if price_row else 0.0
        except Exception:
            unit = 0.0
            a = None
        if a is None:
            continue
        addon_items.append({
            "product_id": a.id,
            "quantity": spec["quantity"],
            "unit_price": unit,
            "name": a.name,
        })

    # Currency
    currency = "GBP"  # all products priced in EUR

    # Create the booking
    try:
        booking = booking_service.create_booking(
            product_type=product_type,
            product_id=product_id,
            travellers_adults=adults,
            travellers_children=children,
            total_amount=total,
            currency=currency,
            user=current_user if current_user.is_authenticated else None,
            guest_email=guest_email if not current_user.is_authenticated else None,
            guest_name=guest_name if not current_user.is_authenticated else None,
            guest_phone=guest_phone if not current_user.is_authenticated else None,
            check_in_date=check_in,
            check_out_date=check_out,
            activity_date=activity_date,
            special_requests=(request.form.get("special_requests") or "").strip() or None,
            addon_items=addon_items,
            how_heard=how_heard,
            payment_method=payment_method,
            travellers=travellers,
        )
    except booking_service.BookingError as exc:
        db.session.rollback()
        flash(f"Could not create booking: {exc}", "danger")
        return redirect(request.referrer or url_for("public.index"))

    # Look up the initial Payment row
    from models import Payment
    payment = db.session.scalar(
        select(Payment)
        .where(Payment.booking_id == booking.id)
        .order_by(Payment.id).limit(1)
    )

    # Try PayPal
    paypal_configured = payment_service.is_configured()
    if paypal_configured and payment is not None:
        try:
            approval_url, _ = payment_service.create_payment(payment)
            db.session.commit()
            return redirect(approval_url)
        except Exception as exc:
            current_app.logger.exception("PayPal create failed: %s", exc)
            flash(
                "We could not reach PayPal. Your booking is saved — "
                "you will be contacted to complete payment.",
                "warning",
            )
            db.session.commit()
            return redirect(url_for("public.booking_confirmation", reference=booking.reference))

    # No PayPal configured — commit and show the confirmation page
    db.session.commit()
    return redirect(url_for("public.booking_confirmation", reference=booking.reference))


# ─── PayPal return ──────────────────────────────────────────────────
@public_bp.route("/booking/paypal/return")
def booking_paypal_return():
    """Handle the PayPal return URL — capture and confirm."""
    payment_id = request.args.get("paymentId", "").strip()
    payer_id = request.args.get("PayerID", "").strip()

    if not payment_id or not payer_id:
        flash("Missing PayPal parameters.", "danger")
        return redirect(url_for("public.index"))

    from models import Payment
    payment = db.session.scalar(
        select(Payment)
        .where(Payment.provider_payment_id == payment_id)
        .limit(1)
    )
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
    """Customer pressed Cancel at PayPal."""
    flash("Payment was cancelled. Your booking is still pending.", "warning")
    return redirect(url_for("public.index"))


# ─── Confirmation ───────────────────────────────────────────────────
@public_bp.route("/booking/confirmation/<reference>")
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

    # Addon subtotal — Decimal to avoid float/Decimal mixing in templates
    from decimal import Decimal as _Dec
    addon_total = sum(
        (_Dec(str(it.line_total or 0)) for it in addon_items),
        _Dec("0.00"),
    )

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
    if booking.product_type == "hotel" and primary_item is not None:
        # Hotel bookings store primary_item.product_id = Room.id.
        # Resolve Room -> Hotel.
        from models import Room as _RoomLookup
        hotel_room_obj = db.session.get(_RoomLookup, primary_item.product_id)
        hotel_obj = (
            db.session.get(Hotel, hotel_room_obj.hotel_id)
            if hotel_room_obj is not None else None
        )
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
            # Only show the booked room, not the whole list
            hotel_rooms = [hotel_room_obj] if hotel_room_obj is not None else []
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
        hotel_room_obj=hotel_room_obj,
        hotel_rooms=hotel_rooms,
        hotel_images=hotel_images,
        hotel_facilities=hotel_facilities,
        activity_obj=activity_obj,
        activity_images=activity_images,
        activity_inclusions=activity_inclusions,
        activity_tips=activity_tips,
        activity_languages=activity_languages,
        activity_price_row=activity_price_row,
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
    )

