path = "templates/public/package_detail.html"
s = open(path, "r", encoding="utf-8").read()

# 1. Hide airline block when land-only
old1 = "{% if opt.airline_name or opt.airline_logo %}"
new1 = "{% if (opt.airline_name or opt.airline_logo) and not opt.is_land_only %}"
assert old1 in s, "airline block anchor not found"
s = s.replace(old1, new1, 1)

# 2. Replace route-or-land-only block
old2 = """{% if opt.flight_from and opt.flight_to %}
                                            <div class="small text-muted mb-3">
                                                <i class="bi bi-airplane"></i>
                                                {{ opt.flight_from }} â†’ {{ opt.flight_to }}
                                            </div>
                                        {% else %}
                                            <div class="small text-muted mb-3">
                                                <i class="bi bi-house"></i> Land only
                                            </div>
                                        {% endif %}"""

new2 = """{% if opt.is_land_only %}
                                            <div class="small text-muted mb-3">
                                                <i class="bi bi-house-fill" style="color:#c85a3e;"></i>
                                                <strong>Land only</strong> — no flights included
                                            </div>
                                        {% elif opt.flight_from and opt.flight_to %}
                                            <div class="small text-muted mb-3">
                                                <i class="bi bi-airplane"></i>
                                                {{ opt.flight_from }} â†’ {{ opt.flight_to }}
                                            </div>
                                        {% endif %}"""

if old2 in s:
    s = s.replace(old2, new2, 1)
    print("option card route/land-only block patched")
else:
    # Fallback: just look for the else block
    old2b = """                                        {% else %}
                                            <div class="small text-muted mb-3">
                                                <i class="bi bi-house"></i> Land only
                                            </div>
                                        {% endif %}"""
    new2b = """                                        {% elif opt.flight_from and opt.flight_to %}
                                            <div class="small text-muted mb-3">
                                                <i class="bi bi-airplane"></i>
                                                {{ opt.flight_from }} â†’ {{ opt.flight_to }}
                                            </div>
                                        {% else %}
                                            <div class="small text-muted mb-3">
                                                <i class="bi bi-house-fill" style="color:#c85a3e;"></i>
                                                <strong>Land only</strong> — no flights included
                                            </div>
                                        {% endif %}"""
    if old2b in s:
        s = s.replace(old2b, new2b, 1)
        print("option card land-only badge patched (fallback)")
    else:
        print("WARN: could not find option card flight block — will need manual patch")

# 3. Sidebar breakdown — hide flights line for land-only
old3 = """        <div class="d-flex justify-content-between small mb-1">
            <span class="text-muted">
                <i class="bi bi-airplane-fill" style="color:#c85a3e;"></i>
                Flights ({{ _opt.airline_name or 'Airline' }})
            </span>
            <span id="breakdown-flight-total">GBP {{ "%.2f"|format(_opt.flight_total) }}</span>
        </div>"""
new3 = """        {% if not _opt.is_land_only %}
        <div class="d-flex justify-content-between small mb-1">
            <span class="text-muted">
                <i class="bi bi-airplane-fill" style="color:#c85a3e;"></i>
                Flights ({{ _opt.airline_name or 'Airline' }})
            </span>
            <span id="breakdown-flight-total">GBP {{ "%.2f"|format(_opt.flight_total) }}</span>
        </div>
        {% endif %}"""
if old3 in s:
    s = s.replace(old3, new3, 1)
    print("sidebar flights line patched")
else:
    print("WARN: sidebar flights line not found — will need manual patch")

open(path, "w", encoding="utf-8").write(s)
print("done")