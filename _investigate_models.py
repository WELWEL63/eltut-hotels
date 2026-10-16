from pathlib import Path
import re

path = Path("blueprints/admin/package_admin.py")
content = path.read_text(encoding="utf-8")

# Find all model imports
models = re.findall(r'from models import \(([^)]+)\)', content, re.DOTALL)
if models:
    print("=" * 60)
    print("MODELS IMPORTED:")
    print("=" * 60)
    for m in models:
        for name in m.split(","):
            name = name.strip()
            if name:
                print(f"  {name}")

# Find all _apply_form_to_package body
start = content.index("def _apply_form_to_package")
remaining = content[start:]
next_def = remaining.find("\ndef ", 10)
if next_def > 0:
    func_body = remaining[:next_def]
else:
    func_body = remaining

print()
print("=" * 60)
print("_apply_form_to_package() FUNCTION:")
print("=" * 60)
print(func_body[:3000])