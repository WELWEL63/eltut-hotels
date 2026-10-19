import sys
import os
from sqlalchemy import select, func, delete

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from extensions import db
from models import PackageFlight, Package, Destination

app = create_app()
app.app_context().push()

# ─── STEP 1: Count current Hurghada links ───
hurghada_dests = db.session.scalars(
    select(Destination).where(Destination.name.ilike('%Hurghada%'))
).all()
hurghada_dest_ids = [d.id for d in hurghada_dests]

hurghada_packages = db.session.scalars(
    select(Package).where(Package.destination_id.in_(hurghada_dest_ids))
).all()
hurghada_pkg_ids = [p.id for p in hurghada_packages]

before_count = db.session.scalar(
    select(func.count(PackageFlight.id))
    .where(PackageFlight.package_id.in_(hurghada_pkg_ids))
)

print("=" * 70)
print(" AUTO-MATCH VERIFICATION TEST")
print("=" * 70)
print(f"\n[STEP 1] BEFORE deletion:")
print(f"  Hurghada packages: {len(hurghada_pkg_ids)}")
print(f"  PackageFlight links: {before_count}")

# ─── STEP 2: Delete all Hurghada PackageFlight links ───
print(f"\n[STEP 2] Deleting all Hurghada PackageFlight links...")
result = db.session.execute(
    delete(PackageFlight).where(PackageFlight.package_id.in_(hurghada_pkg_ids))
)
db.session.commit()
after_delete = db.session.scalar(
    select(func.count(PackageFlight.id))
    .where(PackageFlight.package_id.in_(hurghada_pkg_ids))
)
print(f"  Deleted: {result.rowcount}")
print(f"  Remaining: {after_delete}")

# ─── STEP 3: Run auto-match (preview) ───
print(f"\n[STEP 3] Running preview_matches()...")
from services.flight_matching_service import preview_matches
preview = preview_matches()

print(f"  Total links to create: {preview['total_links']}")
for airport, info in preview['destinations'].items():
    if info['links_to_create'] > 0:
        print(f"    {airport}: {info['links_to_create']} links ({info['packages']} pkgs, {info['valid_combos']} combos)")

# ─── STEP 4: Apply matches ───
print(f"\n[STEP 4] Applying matches...")
from services.flight_matching_service import apply_matches
result = apply_matches()

print(f"  Created: {result['created']}")
print(f"  Errors: {len(result['errors'])}")

# ─── STEP 5: Verify ───
after_count = db.session.scalar(
    select(func.count(PackageFlight.id))
    .where(PackageFlight.package_id.in_(hurghada_pkg_ids))
)

print(f"\n[STEP 5] AFTER auto-match:")
print(f"  PackageFlight links: {after_count}")
print(f"  Expected: {result['created']}")

print(f"\n" + "=" * 70)
if after_count == result['created']:
    print(" ✅ TEST PASSED — Auto-match created exactly the expected number of links!")
elif after_count > 0:
    print(f" ⚠️ Partial success — created {after_count} links (expected {result['created']})")
else:
    print(" ❌ TEST FAILED — No links created!")
print("=" * 70)

# ─── STEP 6: Sample the created links ───
print(f"\n[SAMPLE] 5 random links created:")
sample = db.session.scalars(
    select(PackageFlight)
    .where(PackageFlight.package_id.in_(hurghada_pkg_ids))
    .limit(5)
).all()
for pf in sample:
    ob = pf.outbound_flight
    ib = pf.inbound_flight
    print(f"  PKG {pf.package_id} | PF {pf.id} | {ob.airline} {ob.departure_date} -> {ib.airline} {ib.departure_date} | {pf.label}")
