import re
from pathlib import Path

# Read the admin package routes file
path = Path("blueprints/admin/package_admin.py")
content = path.read_text(encoding="utf-8")

# Find all @admin_bp.route decorators + the function they wrap
routes = []
for match in re.finditer(r'@admin_bp\.route\(([^)]+)\)\s*\ndef (\w+)', content):
    routes.append({
        "route": match.group(1).strip(),
        "func": match.group(2),
        "line": content[:match.start()].count("\n") + 1,
    })

print(f"Found {len(routes)} admin package routes:")
print()
for r in routes:
    print(f"  L{r['line']:<5} {r['func']:<40} {r['route']}")

print()
print("=" * 60)
print(f"File size: {len(content)} chars, {content.count(chr(10))} lines")
print("=" * 60)