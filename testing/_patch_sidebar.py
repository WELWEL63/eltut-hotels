p = 'templates/public/booking_start.html'
with open(p, encoding='utf-8') as f:
    c = f.read()

# ─── Anchor: closing </div> after the "Change" link ───
anchor = '''                                <a href="javascript:history.back()" class="small text-decoration-none ms-2">
                                    Change
                                </a>
                            </div>
                        </div>'''

if anchor not in c:
    print("ANCHOR NOT FOUND")
    idx = c.find("Change</a>")
    if idx == -1:
        idx = c.find("Change")
    print("Context around 'Change':")
    print(repr(c[max(0,idx-150):idx+300]))
    raise SystemExit(1)

# Check we haven't already inserted
if "Your selected flight" in c and "option.airline_name" in c:
    print("Block already present — no change")
    raise SystemExit(0)

insert = anchor + '''
                        {# ─── Selected flight (only if a package option was chosen) ─── #}
                        {% if option and (option.airline_name or option.flight_from or option.luggage_allowance) %}
                            <div class="card-body border-bottom pb-3">
                                <div class="small fw-semibold text-uppercase text-muted mb-2"
                                     style="letter-spacing:.05em; font-size:.7rem;">
                                    <i class="bi bi-airplane text-eltut-terracotta"></i>
                                    Your selected flight
                                </div>
                                <div class="d-flex align-items-center gap-2 mb-2">
                                    {% if option.airline_logo %}
                                        <img src="{{ option.airline_logo }}" alt=""
                                             style="height:32px; max-width:70px; object-fit:contain;"
                                             onerror="this.style.display='none';">
                                    {% endif %}
                                    <div>
                                        <div class="fw-semibold">
                                            {{ option.airline_name or "Multiple airlines" }}
                                        </div>
                                        {% if option.flight_from and option.flight_to %}
                                            <div class="small text-muted">
                                                {{ option.flight_from }} → {{ option.flight_to }}
                                            </div>
                                        {% endif %}
                                    </div>
                                </div>
                                {% if option.departure_date and option.return_date %}
                                    <div class="small text-muted mb-1">
                                        <i class="bi bi-calendar-range"></i>
                                        {{ option.departure_date.strftime("%d %b %Y") }} → {{ option.return_date.strftime("%d %b %Y") }}
                                    </div>
                                {% endif %}
                                {% if option.luggage_allowance %}
                                    <div class="small text-muted">
                                        <i class="bi bi-suitcase"></i>
                                        {{ option.luggage_allowance }} luggage
                                    </div>
                                {% endif %}
                            </div>
                        {% endif %}
'''

c = c.replace(anchor, insert, 1)

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print("PATCHED — booking_start.html updated")
