import io
path = "templates/admin/base.html"
with io.open(path, encoding="utf-8") as f:
    c = f.read()

# Find the Airlines link and insert Flight prices right after
anchor = '<i class="bi bi-airplane"></i> Airlines\n                    </a>'

nav_link = '''<i class="bi bi-airplane"></i> Airlines
                    </a>
                    <a href="{{ url_for('admin.flight_admin_index') }}"
                       class="list-group-item list-group-item-action {% if request.endpoint and request.endpoint.startswith('admin.flight_admin') %}active{% endif %}">
                        <i class="bi bi-cash-coin"></i> Flight prices
                    </a>'''

if 'admin.flight_admin_index' in c:
    print("Nav link already present")
elif anchor in c:
    c = c.replace(anchor, nav_link, 1)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("Nav link added")
else:
    print("Anchor not found")
    idx = c.find('bi-airplane')
    print("Debug:", repr(c[idx-80:idx+120]) if idx > 0 else "no match")