path = "templates/public/package_detail.html"
s = open(path, "r", encoding="utf-8").read()

# 1. Add a "land-only" banner right after the hero card, when
#    every option is land-only
old_hero_end = '''                        <div class="d-flex flex-wrap gap-2 mt-4">'''
new_hero_end = '''                        {% if options and options[0].is_land_only %}
                        <div class="alert alert-info d-flex align-items-center gap-2 mt-4 mb-0" role="alert">
                            <i class="bi bi-info-circle-fill"></i>
                            <div class="small">
                                <strong>Land-only package.</strong>
                                Flights are not included — you'll arrange your own travel.
                                Your hotel, transfers, and <strong>day-by-day itinerary</strong>
                                are all included below.
                            </div>
                        </div>
                        {% endif %}

                        <div class="d-flex flex-wrap gap-2 mt-4">'''
if old_hero_end in s and "Land-only package." not in s:
    s = s.replace(old_hero_end, new_hero_end, 1)
    print("hero banner added")
else:
    print("hero banner already present or anchor not found")

# 2. Adapt the "Available departures" heading when land-only
old_head = '''                            Available departures
                            <span class="subtitle">
                                Pick the flight that suits you ГўВЈвЂќ price updates automatically.
                            </span>'''
new_head = '''                            Available departures
                            <span class="subtitle">
                                {% if options and options[0].is_land_only %}
                                    Land-only package — day-by-day itinerary included.
                                {% else %}
                                    Pick the flight that suits you ГўВЈвЂќ price updates automatically.
                                {% endif %}
                            </span>'''
if old_head in s:
    s = s.replace(old_head, new_head, 1)
    print("departures heading patched")
else:
    print("WARN: departures heading anchor not found")

# 3. Hide "Your selected flight" section when land-only
old_sf = '''                {# ГўвЂќВЈГўвЂќВЈГўвЂќВЈ Your selected flight (live-updating panel) ГўвЂќВЈГўвЂќВЈГўвЂќВЈ #}
                {% if options %}'''
new_sf = '''                {# ГўвЂќВЈГўвЂќВЈГўвЂќВЈ Your selected flight (live-updating panel) ГўвЂќВЈГўвЂќВЈГўвЂќВЈ #}
                {% if options and not options[0].is_land_only %}'''
if old_sf in s:
    s = s.replace(old_sf, new_sf, 1)
    print("selected-flight panel hidden for land-only")
else:
    print("WARN: selected-flight anchor not found")

# 4. Hide sidebar "Your selected flight" block when land-only
old_sel_side = '''                    {% if options %}
                        <div class="card-body border-bottom" id="selected-flight-summary">'''
new_sel_side = '''                    {% if options and not options[0].is_land_only %}
                        <div class="card-body border-bottom" id="selected-flight-summary">'''
if old_sel_side in s:
    s = s.replace(old_sel_side, new_sel_side, 1)
    print("sidebar selected-flight hidden for land-only")
else:
    print("WARN: sidebar selected-flight anchor not found")

open(path, "w", encoding="utf-8").write(s)
print("done")