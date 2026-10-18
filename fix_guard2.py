import io
import re

path = "blueprints/public/booking_routes.py"
with io.open(path, "r", encoding="utf-8") as f:
    content = f.read()

# ── STEP 1: Remove the DUPLICATE / BROKEN guard blocks ────────────────
# We'll remove every occurrence of the guard block (from `if package_flight_id is None:` up to the closing `return redirect(...)`)
guard_pattern = re.compile(
    r"        if package_flight_id is None:\n"
    r"(?:            .*\n|\n)*?"
    r"                return redirect\(request\.referrer or url_for\(\"public\.index\"\)\)\n",
    re.DOTALL
)

# Find all matches
matches = list(guard_pattern.finditer(content))
print(f"Found {len(matches)} guard block(s) to remove.")

for m in reversed(matches):
    content = content[:m.start()] + content[m.end():]

# ── STEP 2: Insert ONE clean guard right after `package_flight_id` parsing ──
# Find the block that ends with `package_flight_id = None` (end of the try/except)
anchor = """        raw_pfid = (request.form.get("package_flight_id") or "").strip()
        if raw_pfid:
            try:
                package_flight_id = int(raw_pfid)
            except ValueError:
                package_flight_id = None"""

new_guard = """        raw_pfid = (request.form.get("package_flight_id") or "").strip()
        if raw_pfid and raw_pfid.lower() != "none":
            try:
                package_flight_id = int(raw_pfid)
            except ValueError:
                package_flight_id = None

        # ── Land-only package check ──────────────────────────────────
        # Load the product FIRST so we can check if it's land-only.
        _product_for_guard = _load_product(PRODUCT_TYPE_PACKAGE, product_id)
        if _product_for_guard is not None and package_flight_id is None:
            from services.package_options_service import options_for_package
            _is_land_only = False
            try:
                _opts = options_for_package(
                    _product_for_guard, check_in, check_out,
                    adults=adults, children=children, tolerance_days=30,
                )
                if _opts:
                    _is_land_only = bool(_opts[0].get("is_land_only", False))
            except Exception as exc:
                current_app.logger.warning("GUARD: options_for_package failed: %s", exc)
                _is_land_only = False

            if not _is_land_only:
                flash(
                    "Please select a departure on the package page before booking.",
                    "warning",
                )
                return redirect(request.referrer or url_for("public.index"))"""

if anchor not in content:
    print("ERROR: Could not find the anchor block for package_flight_id parsing.")
    print("The file may be in an unexpected state.")
    exit()

content = content.replace(anchor, new_guard, 1)

with io.open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("DONE. Guard block replaced with a single clean version that loads the product first.")