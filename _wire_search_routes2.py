path = "blueprints/public/search_routes.py"
lines = open(path, "r", encoding="utf-8").read().splitlines(keepends=True)

# Find the "destinations = search_service.destinations_for_widget()" line
target = None
for i, ln in enumerate(lines):
    if "destinations = search_service.destinations_for_widget()" in ln:
        target = i
        break

assert target is not None, "widget line not found"

# Replace only that line with two lines
lines[target] = (
    "    destinations = search_service.destinations_for_widget()\n"
    "    package_destinations = search_service.destinations_for_package_widget()\n"
)

open(path, "w", encoding="utf-8").writelines(lines)
print(f"patched line {target + 1}")