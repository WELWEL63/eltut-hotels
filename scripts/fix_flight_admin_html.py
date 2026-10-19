import re

file_path = "templates/admin/flight_admin.html"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Extract the misplaced auto-match block
pattern = r'(<!-- ═══════════════════════════════════════════════════════════════ -->\s*<!-- AUTO-MATCH FLIGHTS TO PACKAGES -->.*?<!-- ═══════════════════════════════════════════════════════════════ -->\s*<!-- END AUTO-MATCH -->\s*<!-- ═══════════════════════════════════════════════════════════════ -->)'

match = re.search(pattern, content, re.DOTALL)

if not match:
    print("[ERR] Could not find the auto-match block.")
    exit()

auto_match_block = match.group(1)

# 2. Remove it from the top
content = content.replace(auto_match_block, "", 1)
print("[OK] Removed auto-match block from top")

# 3. Find injection point: after the header buttons div, before the filter form
form_marker = '<form method="GET" class="card shadow-sm mb-3 border-0">'

if form_marker in content:
    content = content.replace(
        form_marker,
        auto_match_block + '\n\n' + form_marker,
        1
    )
    print("[OK] Inserted auto-match block before filter form")
else:
    print("[ERR] Could not find filter form marker")
    exit()

# 4. Verify extends is at the top
lines = content.split('\n')
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped and not stripped.startswith('{#'):
        if 'extends' in stripped:
            print("[OK] extends is at line " + str(i+1) + " (first non-comment line)")
            break
        else:
            print("[WARN] First non-comment line: " + stripped[:80])
            break

# 5. Save
with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("\n[OK] File fixed and saved.")
print("Next: Restart Flask and check /admin/flights")
