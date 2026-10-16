# -*- coding: utf-8 -*-
import io, os

roots = ["blueprints", "services", "templates"]
hits = []

for root in roots:
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if not (fn.endswith(".py") or fn.endswith(".html")):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with io.open(path, encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if '"EUR"' in line or "'EUR'" in line or '€' in line:
                            hits.append(f"{path}:{i}: {line.rstrip()[:150]}")
            except Exception as e:
                hits.append(f"ERR {path}: {e}")

with io.open("_eur_hits.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(hits))

print("Total:", len(hits))
print("Written to _eur_hits.txt")
print()
print("=== FIRST 20 LINES ===")
for h in hits[:20]:
    print(h)