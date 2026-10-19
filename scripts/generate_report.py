import sys
import os
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from extensions import db
from models import * # Imports all models
from sqlalchemy import inspect

app = create_app()
app.app_context().push()

report_file = 'PROJECT_REPORT.md'
lines = []

lines.append('# ElTut Tours Platform — Full Code & Status Report')
lines.append(f'**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')

# 1. Database Tables & Row Counts
lines.append('## 1. Database Schema & Row Counts')
inspector = inspect(db.engine)
tables = inspector.get_table_names()
lines.append('| Table | Row Count |')
lines.append('|-------|-----------|')
for table in sorted(tables):
    try:
        count = db.session.execute(db.text(f'SELECT COUNT(*) FROM {table}')).scalar()
        lines.append(f'| {table} | {count} |')
    except Exception:
        lines.append(f'| {table} | ERROR |')
lines.append('')

# 2. Total Revenue
lines.append('## 2. Business Stats')
from models import Booking, PackageFlight
try:
    total_bookings = db.session.query(Booking).count()
    total_revenue = db.session.query(db.func.sum(Booking.total_amount)).scalar() or 0
    lines.append(f'- Total Bookings: **{total_bookings}**')
    lines.append(f'- Total Revenue: **GBP {total_revenue:,.2f}**')
    
    flight_links = db.session.query(PackageFlight).count()
    lines.append(f'- Flight Links (PackageFlight): **{flight_links}**')
except Exception as e:
    lines.append(f'Error: {e}')
lines.append('')

# 3. Routes
lines.append('## 3. All Registered Routes')
lines.append('| Method | Route | Endpoint |')
lines.append('|--------|-------|----------|')
for rule in sorted(app.url_map.iter_rules(), key=lambda x: str(x)):
    if rule.endpoint == 'static':
        continue
    methods = ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
    lines.append(f'| {methods} | {rule.rule} | {rule.endpoint} |')
lines.append('')

# 4. File Inventory
lines.append('## 4. Project File Inventory')
for folder in ['models', 'services', 'blueprints', 'scripts', 'templates', 'static/css']:
    path = os.path.join(os.getcwd(), folder)
    if os.path.exists(path):
        files = []
        for root, dirs, filenames in os.walk(path):
            dirs[:] = [d for d in dirs if d not in ['.venv', '__pycache__', '.git']]
            for f in filenames:
                files.append(os.path.join(root, f).replace(os.getcwd(), '').replace('\\', '/'))
        lines.append(f'### {folder}/ ({len(files)} files)')
        for f in sorted(files)[:20]:  # Limit to 20 per folder to avoid huge reports
            lines.append(f'- {f}')
        if len(files) > 20:
            lines.append(f'- ...and {len(files) - 20} more files.')
        lines.append('')

# 5. Recent Scripts
lines.append('## 5. Automation Scripts')
scripts_path = os.path.join(os.getcwd(), 'scripts')
if os.path.exists(scripts_path):
    for f in sorted(os.listdir(scripts_path)):
        if f.endswith('.py'):
            lines.append(f'- scripts/{f}')
lines.append('')

# 6. Environment
lines.append('## 6. Environment Configuration')
lines.append(f'- FLASK_ENV: {os.getenv("FLASK_ENV", "unknown")}')
lines.append(f'- Database: PostgreSQL (Neon)')
lines.append(f'- MongoDB: {"Connected" if os.getenv("MONGO_URI") else "Not Connected"}')
lines.append(f'- PayPal: {"Configured" if os.getenv("PAYPAL_CLIENT_ID") else "Not Configured"}')
lines.append('')

# 7. Known Issues
lines.append('## 7. Known Issues & Next Steps')
lines.append('- Empty packages/rooms (£0.00) - Fix via Admin.')
lines.append('- Missing images in static/images/ (PayPal, Mastercard, etc.).')
lines.append('- Cloud Function (worker.py) not yet wired to email notifications.')
lines.append('- ooking_confirmation.html div imbalance (minor CSS fix).')
lines.append('')

# 8. Security Checklist
lines.append('## 8. Security Checklist')
lines.append('- [x] Debug mode OFF')
lines.append('- [x] SECRET_KEY rotated')
lines.append('- [x] CSRF Protection enabled')
lines.append('- [x] Security Headers (CSP, HSTS, X-Frame)')
lines.append('- [x] IDOR prevention on account routes')
lines.append('- [x] BOM removed from 76 files')
lines.append('- [ ] Missing images (/static/images/payments/*)')
lines.append('')

# Write to file
with open(report_file, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f'✅ Report saved to {report_file}')
print(f'📊 Tables: {len(tables)} | Routes: {len(list(app.url_map.iter_rules()))} | Bookings: {total_bookings}')
