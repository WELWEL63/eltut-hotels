path = "templates/public/booking_start.html"
s = open(path, "r", encoding="utf-8").read()

# 1. Header block: hotel name + stars + room + meal plan + destination + address
old = '''                        {# Header — hotel/room/destination #}
                        <div class="card-body border-bottom pb-3">
                            <div class="d-flex align-items-start gap-2 mb-2">
                                <i class="bi bi-{% if product_type == 'hotel' %}building{% elif product_type == 'package' %}suitcase-lg{% else %}compass{% endif %} text-eltut-terracotta" style="font-size:1.4rem;"></i>
                                <div class="flex-grow-1">
                                    <div class="fw-bold small">{{ hotel or meta.name }}</div>
                                    {% if room %}
                                        <div class="text-muted small">{{ room }}</div>
                                    {% endif %}
                                </div>
                            </div>
                            {% if destination %}
                                <div class="small text-muted">
                                    <i class="bi bi-geo-alt"></i> {{ destination }}
                                </div>
                            {% endif %}
                        </div>'''

new = '''                        {# Header — hotel/room/destination #}
                        <div class="card-body border-bottom pb-3">
                            <div class="d-flex align-items-start gap-2 mb-2">
                                <i class="bi bi-{% if product_type == 'hotel' %}building{% elif product_type == 'package' %}suitcase-lg{% else %}compass{% endif %} text-eltut-terracotta" style="font-size:1.4rem;"></i>
                                <div class="flex-grow-1">
                                    {% if meta.hotel %}
                                        <div class="fw-bold">{{ meta.hotel }}</div>
                                        {% if meta.stars %}
                                            <div class="small" style="color:#f2c964;">
                                                {% for _ in range(meta.stars|int) %}<i class="bi bi-star-fill"></i>{% endfor %}
                                                <span class="text-muted ms-1" style="font-size:.75rem;">{{ meta.stars }}-star</span>
                                            </div>
                                        {% endif %}
                                        {% if meta.room %}
                                            <div class="text-muted small mt-1">
                                                <i class="bi bi-door-open"></i> {{ meta.room }}
                                                {% if meta.meal_plan %}
                                                    <span class="mx-1">&middot;</span>
                                                    <i class="bi bi-egg-fried"></i> {{ meta.meal_plan|replace("_", " ")|title }}
                                                {% endif %}
                                                {% if meta.max_occupancy %}
                                                    <span class="mx-1">&middot;</span>
                                                    <i class="bi bi-people"></i> Up to {{ meta.max_occupancy }}
                                                {% endif %}
                                            </div>
                                        {% endif %}
                                    {% else %}
                                        <div class="fw-bold">{{ meta.name }}</div>
                                    {% endif %}
                                </div>
                            </div>
                            {% if meta.destination %}
                                <div class="small text-muted mb-1">
                                    <i class="bi bi-geo-alt-fill" style="color:#c85a3e;"></i>
                                    {{ meta.destination }}
                                    {% if meta.address %} &mdash; {{ meta.address }}{% endif %}
                                </div>
                            {% endif %}
                            {% if meta.hotel_slug %}
                                <a href="{{ url_for('public.hotel_detail', slug=meta.hotel_slug) }}"
                                   class="small text-decoration-none">
                                    <i class="bi bi-info-circle"></i> View hotel details
                                </a>
                            {% endif %}
                        </div>'''

assert old in s, "header block not found"
s = s.replace(old, new, 1)

# 2. Add a small "what's included" summary row after the dates
old2 = '''                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <div>
                                    {% if form_defaults.check_in and form_defaults.check_out %}
                                        <div class="small">
                                            <i class="bi bi-calendar-range text-eltut-terracotta"></i>
                                            <strong>{{ form_defaults.check_in.strftime("%d %b %Y") }}</strong>
                                            →
                                            <strong>{{ form_defaults.check_out.strftime("%d %b %Y") }}</strong>
                                        </div>
                                    {% elif form_defaults.activity_date %}
                                        <div class="small">
                                            <i class="bi bi-calendar-event text-eltut-terracotta"></i>
                                            <strong>{{ form_defaults.activity_date.strftime("%d %b %Y") }}</strong>
                                        </div>
                                    {% endif %}
                                    <div class="small text-muted mt-1">
                                        {% if pricing.nights %}
                                            <i class="bi bi-moon-stars"></i> {{ pricing.nights }} night{{ "" if pricing.nights == 1 else "s" }}
                                            ·
                                        {% endif %}
                                        <i class="bi bi-people"></i>
                                        {{ form_defaults.adults }} adult{{ "" if form_defaults.adults == 1 else "s" }}
                                        {% if form_defaults.children %}
                                            + {{ form_defaults.children }} child{{ "" if form_defaults.children == 1 else "ren" }}
                                        {% endif %}
                                    </div>
                                </div>
                                <a href="javascript:history.back()" class="small text-decoration-none ms-2">
                                    Change
                                </a>
                            </div>'''

new2 = '''                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <div>
                                    {% if form_defaults.check_in and form_defaults.check_out %}
                                        <div class="small">
                                            <i class="bi bi-calendar-range text-eltut-terracotta"></i>
                                            <strong>{{ form_defaults.check_in.strftime("%d %b %Y") }}</strong>
                                            →
                                            <strong>{{ form_defaults.check_out.strftime("%d %b %Y") }}</strong>
                                        </div>
                                    {% elif form_defaults.activity_date %}
                                        <div class="small">
                                            <i class="bi bi-calendar-event text-eltut-terracotta"></i>
                                            <strong>{{ form_defaults.activity_date.strftime("%d %b %Y") }}</strong>
                                        </div>
                                    {% endif %}
                                    <div class="small text-muted mt-1">
                                        {% if pricing.nights %}
                                            <i class="bi bi-moon-stars"></i> {{ pricing.nights }} night{{ "" if pricing.nights == 1 else "s" }}
                                            ·
                                        {% endif %}
                                        <i class="bi bi-people"></i>
                                        {{ form_defaults.adults }} adult{{ "" if form_defaults.adults == 1 else "s" }}
                                        {% if form_defaults.children %}
                                            + {{ form_defaults.children }} child{{ "" if form_defaults.children == 1 else "ren" }}
                                        {% endif %}
                                    </div>
                                </div>
                                <a href="javascript:history.back()" class="small text-decoration-none ms-2">
                                    Change
                                </a>
                            </div>

                            {# What's included — brief reassurance #}
                            <div class="small text-muted pt-2 mt-2" style="border-top:1px dashed rgba(0,0,0,0.08);">
                                {% if product_type == 'hotel' %}
                                    <div class="mb-1"><i class="bi bi-check-circle-fill text-success"></i> Room &amp; meal plan</div>
                                    <div><i class="bi bi-check-circle-fill text-success"></i> Taxes &amp; service included</div>
                                {% elif product_type == 'package' %}
                                    <div class="mb-1"><i class="bi bi-check-circle-fill text-success"></i> Flights &amp; hotel</div>
                                    <div><i class="bi bi-check-circle-fill text-success"></i> Transfers &amp; taxes</div>
                                {% else %}
                                    <div class="mb-1"><i class="bi bi-check-circle-fill text-success"></i> Guided experience</div>
                                    <div><i class="bi bi-check-circle-fill text-success"></i> All entry fees</div>
                                {% endif %}
                            </div>'''

assert old2 in s, "dates/party block not found"
s = s.replace(old2, new2, 1)

open(path, "w", encoding="utf-8").write(s)
print("booking_start.html sidebar enriched")