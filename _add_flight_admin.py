import io
path = "blueprints/admin/__init__.py"
with io.open(path, encoding="utf-8") as f:
    c = f.read()

old = "from blueprints.admin import offer_admin        # noqa: E402,F401"
new = """from blueprints.admin import offer_admin        # noqa: E402,F401
from blueprints.admin import flight_admin       # noqa: E402,F401"""

if "flight_admin" in c:
    print("Already imported")
else:
    c = c.replace(old, new, 1)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("flight_admin registered")