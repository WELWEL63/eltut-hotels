path = "blueprints/public/search_routes.py"
lines = open(path, "r", encoding="utf-8").read().splitlines(keepends=True)

target = None
for i, ln in enumerate(lines):
    if "destinations=destinations," in ln:
        target = i
        break

assert target is not None, "destinations=destinations, line not found"

# Insert package_destinations= right after
lines.insert(target + 1, "        package_destinations=package_destinations,\n")

open(path, "w", encoding="utf-8").writelines(lines)
print(f"inserted at line {target + 2}")