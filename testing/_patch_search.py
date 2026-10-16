import re
p = 'services/search_service.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# Show every USD occurrence with context
print("USD occurrences in search_service.py:")
print("=" * 70)
for i, m in enumerate(re.finditer(r'"USD"|\'USD\'', c), 1):
    line_no = c[:m.start()].count("\n") + 1
    line_start = c.rfind("\n", 0, m.start()) + 1
    line_end = c.find("\n", m.end())
    if line_end == -1:
        line_end = len(c)
    line = c[line_start:line_end].rstrip()
    print(f"{i}. line {line_no}: {line.strip()}")

# Count before
before = c.count('"USD"') + c.count("'USD'")

# Replace
c = c.replace('"USD"', '"EUR"')
c = c.replace("'USD'", "'EUR'")

after = c.count('"USD"') + c.count("'USD'")

print(f"\nBefore: {before} occurrences")
print(f"After: {after} occurrences")
print(f"Replaced: {before - after}")

if before != after:
    with open(p, 'w', encoding='utf-8') as f:
        f.write(c)
    print("✅ FILE WRITTEN")
else:
    print("⚠️ NO CHANGES MADE — file not written")
