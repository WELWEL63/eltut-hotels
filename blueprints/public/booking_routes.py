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
            "currency": price_row.currency if price_row else "EUR",
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
            "currency": "EUR",
            "location": hotel.destination_id if hotel else None,
            "hotel": hotel.name if hotel else None,
            "room": product.type,
            "destination": dest.name if dest else None,
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
            "currency": price_row.currency if price_row else "EUR",
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
    currency = "EUR"

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
            currency = rate.currency or "EUR"

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


def _package_pricing(package: Package, adults: int, children: int) -> dict:
    row = db.session.scalars(
        select(PackagePrice)
        .where(PackagePrice.package_id == package.id)
        .order_by(PackagePrice.id.asc()).limit(1)
    ).first()
    if row is None:
        return {
            "adult_rate": None, "child_rate": None, "nights": package.duration_nights,
            "per_night": None, "total": None, "currency": "EUR",
        }
    adult_rate = float(row.adult_price or 0)
    child_rate = float(row.child_price or 0)
    per_person = adult_rate * adults + child_rate * children
    return {
        "adult_rate": adult_rate,
        "child_rate": child_rate,
        "nights": package.duration_nights,
        "per_night": None,
        "per_person": per_person,
        "total": per_person,
        "currency": row.currency or "EUR",
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
            "per_night": None, "total": None, "currency": "EUR",
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
        "currency": row.currency or "EUR",
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

    # ─── Optional departure option (packages only) ─────────────────
    option = None
    raw_option_id = (request.args.get("option_id") or "").strip()
    if product_type == "package" and raw_option_id:
        try:
            option_id = int(raw_option_id)
        except ValueError:
            option_id = None
        if option_id:
            candidate = db.session.get(PackageOption, option_id)
            if candidate and candidate.package_id == product.id and candidate.is_active:
                option = candidate

    meta = _product_meta(product_type, product)

    # If a valid option was selected, override meta's price fields
    if option is not None and option.price is not None:
        try:
            meta["price_adult"] = float(option.price.adult_price)
        except Exception:
            pass
        try:
            meta["price_child"] = float(option.price.child_price)
        except Exception:
            pass
        if option.price.currency:
            meta["currency"] = option.price.currency
        if option.departure_date:
            meta["default_start"] = option.departure_date.isoformat()

    # ─── Compute the price for the stay (server-side) ──────────────
    try:
        if product_type == PRODUCT_TYPE_HOTEL:
            pricing = _room_stay_pricing(product, check_in, check_out, adults, children)
        elif product_type == PRODUCT_TYPE_PACKAGE:
            # Use the selected departure option price if we have one.
            # Otherwise fall back to the package's first price row.
            if option is not None and option.price is not None:
                _adult = float(option.price.adult_price or 0)
                _child = float(option.price.child_price or 0)
                pricing = {
                    "adult_rate": _adult,
                    "child_rate": _child,
                    "nights": product.duration_nights,
                    "per_night": None,
                    "per_person": _adult,
                    "total": (_adult * adults) + (_child * children),
                    "currency": option.price.currency or "EUR",
                }
            else:
                pricing = _package_pricing(product, adults, children)
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
        flight = option.flight
        price = option.price
        # Resolve airline logo (best-effort via Airline FK, then name match)
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
            "label": option.display_label,
            "departure_date": option.departure_date,
            "return_date": option.return_date,
            "flight_from": flight.flight_from if flight else None,
            "flight_to": flight.flight_to if flight else None,
            "airline_name": flight.airline_name if flight else None,
            "airline_logo": airline_logo,
            "luggage_allowance": flight.luggage_allowance if flight else None,
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

    # Compute the total server-side
    try:
        total = pricing_service.compute_booking_total(
            product_type=product_type,
            product_id=product_id,
            adults=adults,
            children=children,
            check_in=check_in,
            check_out=check_out,
            addons=addon_specs,
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
    currency = "EUR"  # all products priced in EUR

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
    return render_template(
        "public/booking_confirmation.html",
        booking=booking,
        payment_service_configured=payment_service.is_configured(),
    )

