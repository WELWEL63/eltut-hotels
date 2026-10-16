from pathlib import Path
import re

path = Path("templates/admin/package_form.html")
content = path.read_text(encoding="utf-8")
lines = content.split("\n")

print(f"Template: {len(lines)} lines")
print()

# Find section headers (usually comment blocks with ═ or #)
print("=" * 60)
print("SECTIONS IN THE FORM:")
print("=" * 60)

for i, line in enumerate(lines, 1):
    stripped = line.strip()
    # Look for comment headers
    if stripped.startswith("{#") and ("─" in stripped or "═" in stripped or "─" in stripped):
        # Get the next line too
        next_line = lines[i] if i < len(lines) else ""
        text = next_line.strip().rstrip("#}").strip()
        if text:
            print(f"  L{i:<5} {text[:80]}")

print()
print("=" * 60)
print("ALL <form> TAGS:")
print("=" * 60)
for i, line in enumerate(lines, 1):
    if "<form" in line:
        print(f"  L{i:<5} {line.strip()[:100]}")

print()
print("=" * 60)
print("ALL 'name=' INPUT FIELDS (first 60):")
print("=" * 60)
count = 0
for i, line in enumerate(lines, 1):
    m = re.search(r'name="([^"]+)"', line)
    if m:
        count += 1
        if count <= 60:
            print(f"  L{i:<5} {m.group(1)}")
        if count == 60:
            print(f"  ... (more)")
            break