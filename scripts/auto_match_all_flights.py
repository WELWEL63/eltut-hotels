import sys
import os
from datetime import timedelta
from collections import defaultdict

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from extensions import db
from models import Package, PackageFlight, FlightPrice, Room, Destination
from sqlalchemy import select

app = create_app()
app.app_context().push()

# Map destination names to their airport codes
AIRPORT_MAP = {
    'hurghada': 'HRG',
    'sharm el sheikh': 'SSH',
    'luxor': 'LXR',
    'aswan': 'ASW',
    'marsa alam': 'RMF',
    'taba': 'TCP',
    'el gouna': 'HRG',
    'sahl hasheesh': 'HRG',
    'soma bay': 'HRG',
    'safaga': 'HRG',
    'nile cruise': 'LXR'
}

print("==================================================")
print(" 🚀 STARTING SMART FLIGHT MATCHING FOR ALL CITIES")
print("==================================================\n")

packages = db.session.scalars(select(Package).where(Package.is_active == True)).all()
all_dests = db.session.scalars(select(Destination)).all()

# Group packages by airport code
packages_by_airport = defaultdict(list)
for pkg in packages:
    room = db.session.get(Room, pkg.room_id)
    if not room or not room.base_price_per_night or room.base_price_per_night <= 0:
        continue # Skip broken rooms
        
    dest = db.session.get(Destination, pkg.destination_id)
    if not dest:
        continue
        
    airport = AIRPORT_MAP.get(dest.name.lower().strip())
    if not airport and dest.airport_code:
        airport = dest.airport_code.strip().upper()
        
    if airport:
        packages_by_airport[airport].append(pkg)

total_inserted = 0

# Process each airport one by one
for airport, pkgs in packages_by_airport.items():
    print(f"Processing Airport: {airport} ({len(pkgs)} packages found)...")
    
    # Fetch flights for this specific airport
    out_flights = db.session.scalars(
        select(FlightPrice)
        .where(FlightPrice.direction == 'out')
        .where(FlightPrice.destination.ilike(f'%{airport}%'))
    ).all()
    
    back_flights = db.session.scalars(
        select(FlightPrice)
        .where(FlightPrice.direction == 'back')
        .where(FlightPrice.origin.ilike(f'%{airport}%'))
    ).all()
    
    if not out_flights or not back_flights:
        print(f"  ⚠️ Skipping {airport}: No flights found in database.\n")
        continue
        
    print(f"  Found {len(out_flights)} outbound and {len(back_flights)} return flights.")
    
    # Build valid combinations (6 to 15 nights)
    valid_combos = []
    for back_f in back_flights:
        valid_outs = [
            out_f for out_f in out_flights 
            if 6 <= (back_f.departure_date - out_f.departure_date).days <= 15
        ]
        if not valid_outs:
            continue
        cheapest_out = min(valid_outs, key=lambda x: float(x.price_gbp))
        nights = (back_f.departure_date - cheapest_out.departure_date).days
        
        label = f"{cheapest_out.airline} ➔ {back_f.airline} ({nights} nights)"
        if cheapest_out.airline.lower() == back_f.airline.lower():
            label = f"{cheapest_out.airline} ({nights} nights)"
            
        valid_combos.append({
            'out': cheapest_out,
            'back': back_f,
            'label': label
        })
        
    print(f"  Built {len(valid_combos)} valid flight combinations.")
    
    if not valid_combos:
        print()
        continue

    # Insert links for these packages
    inserted_here = 0
    for combo in valid_combos:
        for pkg in pkgs:
            # Check for duplicates
            existing = db.session.scalar(
                select(PackageFlight)
                .where(PackageFlight.package_id == pkg.id)
                .where(PackageFlight.outbound_flight_id == combo['out'].id)
                .where(PackageFlight.inbound_flight_id == combo['back'].id)
            )
            if existing:
                continue
                
            pf = PackageFlight(
                package_id=pkg.id,
                outbound_flight_id=combo['out'].id,
                inbound_flight_id=combo['back'].id,
                label=combo['label'],
                sort_order=0,
                is_active=True
            )
            db.session.add(pf)
            inserted_here += 1
            
    db.session.commit()
    print(f"  ✅ Successfully linked {inserted_here} flight cards for {airport}.\n")
    total_inserted += inserted_here

print("==================================================")
print(f" 🎉 ALL DONE! Total PackageFlight links created: {total_inserted}")
print("==================================================")
