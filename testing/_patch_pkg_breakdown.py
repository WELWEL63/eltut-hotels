p = 'templates/public/booking_start.html'
with open(p, encoding='utf-8') as f:
    c = f.read()

# The exact anchor — the package else-branch
old = """                                            {% else %}
                                                Package — per person
                                            {% endif %}"""

new = """                                            {% else %}
                                                Package — {{ pricing.currency }} {{ "%.2f"|format(pricing.adult_rate or 0) }} × {{ form_defaults.adults }} adult{{ "" if form_defaults.adults == 1 else "s" }}
                                                {% if form_defaults.children and pricing.child_rate and pricing.child_rate > 0 %}
                                                    + {{ pricing.currency }} {{ "%.2f"|format(pricing.child_rate) }} × {{ form_defaults.children }} child{{ "" if form_defaults.children == 1 else "ren" }}
                                                {% endif %}
                                            {% endif %}"""

if old not in c:
    print("ANCHOR NOT FOUND")
    idx = c.find("Package — per person")
    if idx >= 0:
        print("Context:")
        print(repr(c[max(0,idx-300):idx+100]))
    raise SystemExit(1)

if "Package — {{ pricing.currency }}" in c:
    print("Already patched — no change")
    raise SystemExit(0)

c = c.replace(old, new, 1)

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print("PATCHED — package line now shows adult + child breakdown")
