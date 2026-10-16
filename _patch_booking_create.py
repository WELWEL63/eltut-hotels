path = "blueprints/public/booking_routes.py"
lines = open(path, "r", encoding="utf-8").read().splitlines(keepends=True)

# Locate the "# Compute the total server-side" block
start = None
end = None
for i, ln in enumerate(lines):
    if "Compute the total server-side" in ln:
        start = i
    if start is not None and "return redirect(request.referrer or url_for(\"public.index\"))" in ln and i > start:
        end = i
        break

assert start is not None and end is not None, f"markers not found: {start} {end}"

new_block = '''    # Package flight card (packages only) — the single source of
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
'''

lines[start-1:end+1] = [new_block]
open(path, "w", encoding="utf-8").writelines(lines)
print("booking_create patched")