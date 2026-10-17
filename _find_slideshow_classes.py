import re
from pathlib import Path

found = set()
for f in list(Path("templates").rglob("*.html")) + list(Path("static/css").rglob("*.css")):
    text = f.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r"\.(slide[\w-]*|hero[\w-]*|show[\w-]*)\b", text):
        found.add(m.group(1))

for name in sorted(found):
    print(name)
