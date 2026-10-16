lines = open("templates/public/package_detail.html", encoding="utf-8").read().splitlines()
# Find the line where <aside> opens
aside_line = None
for i, l in enumerate(lines, 1):
    if "<aside" in l:
        aside_line = i
        break
print(f"aside at line: {aside_line}")

# Trace depth from line 22 (pkg-main open) to aside
depth = 0
for i in range(21, aside_line):
    line = lines[i]
    depth += line.count("<div")
    depth -= line.count("</div>")
    # print transitions only every time depth would go negative or 0
    if depth <= 1 and i > 22:
        print(f"line {i+1}: depth={depth}  {line.strip()[:80]}")
        if depth == 0:
            print("  ^ pkg-main closed here")
