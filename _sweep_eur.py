# -*- coding: utf-8 -*-
import io, os

roots = ["blueprints", "services", "templates"]
changed = []

for root in roots:
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if not (fn.endswith(".py") or fn.endswith(".html")):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with io.open(path, encoding="utf-8") as f:
                    c = f.read()
            except Exception as e:
                print(f"SKIP {path}: {e}")
                continue

            orig = c
            # Replace EUR currency codes only — not the word "Europe" etc.
            c = c.replace('"EUR"', '"GBP"')
            c = c.replace("'EUR'", "'GBP'")
            c = c.replace('€', '£')

            if c != orig:
                with io.open(path, "w", encoding="utf-8") as f:
                    f.write(c)
                changed.append(path)

print(f"Files changed: {len(changed)}")
for p in changed:
    print(f"  {p}")