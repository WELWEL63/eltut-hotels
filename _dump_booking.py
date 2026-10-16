path = "blueprints/public/booking_routes.py"
s = open(path, "r", encoding="utf-8").read()
lines = s.splitlines()

def dump(a, b, label):
    print(f"--- {label} (lines {a}-{b}) ---")
    for i in range(a-1, min(b, len(lines))):
        print(f"{i+1:4} | {lines[i]!r}")

dump(226, 250, "_package_pricing head")
print()
dump(310, 375, "booking_start option + pricing")