p = 'templates/public/index.html'
with open(p, encoding='utf-8') as f:
    c = f.read()

replacements = [
    # ─── HOTELS ───
    (
        '''{% for h in featured_hotels %}
                {% set img = h.images[0].url if h.images else None %}''',
        '''{% for item in featured_hotels %}
                {% set h = item.obj %}
                {% set img = h.images[0].url if h.images else None %}'''
    ),
    (
        '''<span class="product-price">EUR&nbsp;{{ h.cheapest_price or '—' }}</span>''',
        '''<span class="product-price">EUR&nbsp;{{ "%.2f"|format(item.price) if item.price else '—' }}</span>'''
    ),
    # ─── PACKAGES ───
    (
        '''{% for p in featured_packages %}
                {% set img = p.images[0].url if p.images else None %}''',
        '''{% for item in featured_packages %}
                {% set p = item.obj %}
                {% set img = p.images[0].url if p.images else None %}'''
    ),
    (
        '''<span class="product-price">EUR&nbsp;{{ p.cheapest_price or '—' }}</span>''',
        '''<span class="product-price">EUR&nbsp;{{ "%.2f"|format(item.price) if item.price else '—' }}</span>'''
    ),
    # ─── ACTIVITIES ───
    (
        '''{% for a in featured_activities %}
                {% set img = a.images[0].url if a.images else None %}''',
        '''{% for item in featured_activities %}
                {% set a = item.obj %}
                {% set img = a.images[0].url if a.images else None %}'''
    ),
    (
        '''<span class="product-price">EUR&nbsp;{{ a.cheapest_price or '—' }}</span>''',
        '''<span class="product-price">EUR&nbsp;{{ "%.2f"|format(item.price) if item.price else '—' }}</span>'''
    ),
]

success = 0
failed = []
for old, new in replacements:
    if old in c:
        c = c.replace(old, new, 1)
        success += 1
    else:
        failed.append(old[:60] + "...")

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)

print(f"Applied {success}/{len(replacements)} replacements")
if failed:
    print("Failed anchors:")
    for f_ in failed:
        print(f"  {f_}")
