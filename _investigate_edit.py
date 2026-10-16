from pathlib import Path

path = Path("blueprints/admin/package_admin.py")
content = path.read_text(encoding="utf-8")

# Find the package_edit function
start = content.index("def package_edit")
# Find the next def at the same indent level (or EOF)
remaining = content[start:]
next_def = remaining.find("\ndef ", 10)
if next_def < 0:
    next_def = len(remaining)
func_body = remaining[:next_def]

print("=" * 60)
print("FULL package_edit() FUNCTION:")
print("=" * 60)
print(func_body)