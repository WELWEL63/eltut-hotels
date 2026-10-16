path = "templates/public/booking_start.html"
s = open(path, "r", encoding="utf-8").read()

anchor = '''            <input type="hidden" name="product_id" value="{{ product.id }}">'''
insert = '''            <input type="hidden" name="product_id" value="{{ product.id }}">
            {% if option and option.id %}
                <input type="hidden" name="package_flight_id" value="{{ option.id }}">
            {% endif %}'''

if 'name="package_flight_id"' in s:
    print("already present")
else:
    assert anchor in s, "product_id input not found"
    s = s.replace(anchor, insert, 1)
    open(path, "w", encoding="utf-8").write(s)
    print("inserted package_flight_id hidden input")