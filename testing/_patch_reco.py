p = 'services/recommendation_service.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# Show every USD in the file
import re
print("Found USD occurrences:")
for m in re.finditer(r'"USD"|\'USD\'', c):
    start = max(0, m.start() - 30)
    end = min(len(c), m.end() + 30)
    print(f"  char {m.start()}: ...{c[start:end]!r}...")

# Replace all "USD" with "EUR" (both quote styles)
before_count = c.count('"USD"') + c.count("'USD'")
c = c.replace('"USD"', '"EUR"')
c = c.replace("'USD'", "'EUR'")
after_count = c.count('"USD"') + c.count("'USD'")

print(f"\nReplaced {before_count - after_count} occurrences")

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)

print("DONE")
