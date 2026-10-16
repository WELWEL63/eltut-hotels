path = "templates/public/_search_widget.html"
lines = open(path, "r", encoding="utf-8").read().splitlines(keepends=True)

# Find all lines with "for d in _dests"
hits = [i for i, ln in enumerate(lines) if "in _dests" in ln]
print("hits at lines:", [i + 1 for i in hits])

# Second occurrence (index 1) is the package tab
assert len(hits) == 3, f"expected 3 loops, found {len(hits)}"
target = hits[1]
lines[target] = lines[target].replace("in _dests", "in _pkg_dests")
print(f"patched line {target + 1}")

open(path, "w", encoding="utf-8").writelines(lines)