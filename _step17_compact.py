path = "templates/public/_filters_sidebar.html"
s = open(path, "r", encoding="utf-8").read()

# Wrap destination/dates/travellers groups with {% if not compact %}

# 1. Destination group
old_dest = '''        {# ── Destination ─────────────────────────────────────────── #}
        <div class="eltut-filters-group">
          <label class="eltut-filters-label" for="ef-destination">
            <i class="bi bi-geo-alt-fill"></i> Destination
          </label>
          <select name="destination" id="ef-destination" class="eltut-filters-select">
            <option value="">Anywhere</option>
            {% for d in destinations %}
              <option value="{{ d.slug }}" {% if _qs.destination == d.slug %}selected{% endif %}>
                {{ d.name }}
              </option>
            {% endfor %}
          </select>
        </div>'''

new_dest = '''        {# ── Destination (hidden when widget at top handles it) ──── #}
        {% if not compact %}
        <div class="eltut-filters-group">
          <label class="eltut-filters-label" for="ef-destination">
            <i class="bi bi-geo-alt-fill"></i> Destination
          </label>
          <select name="destination" id="ef-destination" class="eltut-filters-select">
            <option value="">Anywhere</option>
            {% for d in destinations %}
              <option value="{{ d.slug }}" {% if _qs.destination == d.slug %}selected{% endif %}>
                {{ d.name }}
              </option>
            {% endfor %}
          </select>
        </div>
        {% else %}
        <input type="hidden" name="destination" value="{{ _qs.destination or '' }}">
        {% endif %}'''

assert old_dest in s, "destination group not found"
s = s.replace(old_dest, new_dest, 1)

# 2. Hotel stay dates
old_hd = '''          <div class="eltut-filters-group">
            <label class="eltut-filters-label">
              <i class="bi bi-calendar-range"></i> Stay dates
            </label>
            <div class="row g-2">
              <div class="col-6">
                <input type="date" name="check_in" class="eltut-filters-input"
                       value="{{ _qs.check_in or '' }}">
              </div>
              <div class="col-6">
                <input type="date" name="check_out" class="eltut-filters-input"
                       value="{{ _qs.check_out or '' }}">
              </div>
            </div>
          </div>'''

new_hd = '''          {% if not compact %}
          <div class="eltut-filters-group">
            <label class="eltut-filters-label">
              <i class="bi bi-calendar-range"></i> Stay dates
            </label>
            <div class="row g-2">
              <div class="col-6">
                <input type="date" name="check_in" class="eltut-filters-input"
                       value="{{ _qs.check_in or '' }}">
              </div>
              <div class="col-6">
                <input type="date" name="check_out" class="eltut-filters-input"
                       value="{{ _qs.check_out or '' }}">
              </div>
            </div>
          </div>
          {% else %}
          <input type="hidden" name="check_in" value="{{ _qs.check_in or '' }}">
          <input type="hidden" name="check_out" value="{{ _qs.check_out or '' }}">
          {% endif %}'''

assert old_hd in s, "hotel stay dates group not found"
s = s.replace(old_hd, new_hd, 1)

# 3. Package travel dates
old_pd = '''          <div class="eltut-filters-group">
            <label class="eltut-filters-label">
              <i class="bi bi-calendar-range"></i> Travel dates
            </label>
            <div class="row g-2">
              <div class="col-6">
                <input type="date" name="check_in" class="eltut-filters-input"
                       value="{{ _qs.check_in or '' }}">
              </div>
              <div class="col-6">
                <input type="date" name="check_out" class="eltut-filters-input"
                       value="{{ _qs.check_out or '' }}">
              </div>
            </div>
          </div>'''

new_pd = '''          {% if not compact %}
          <div class="eltut-filters-group">
            <label class="eltut-filters-label">
              <i class="bi bi-calendar-range"></i> Travel dates
            </label>
            <div class="row g-2">
              <div class="col-6">
                <input type="date" name="check_in" class="eltut-filters-input"
                       value="{{ _qs.check_in or '' }}">
              </div>
              <div class="col-6">
                <input type="date" name="check_out" class="eltut-filters-input"
                       value="{{ _qs.check_out or '' }}">
              </div>
            </div>
          </div>
          {% else %}
          <input type="hidden" name="check_in" value="{{ _qs.check_in or '' }}">
          <input type="hidden" name="check_out" value="{{ _qs.check_out or '' }}">
          {% endif %}'''

assert old_pd in s, "package travel dates group not found"
s = s.replace(old_pd, new_pd, 1)

# 4. Activity date
old_ad = '''          <div class="eltut-filters-group">
            <label class="eltut-filters-label" for="ef-date">
              <i class="bi bi-calendar-event"></i> Date
            </label>
            <input type="date" name="date" id="ef-date" class="eltut-filters-input"
                   value="{{ _qs.date or '' }}">
          </div>'''

new_ad = '''          {% if not compact %}
          <div class="eltut-filters-group">
            <label class="eltut-filters-label" for="ef-date">
              <i class="bi bi-calendar-event"></i> Date
            </label>
            <input type="date" name="date" id="ef-date" class="eltut-filters-input"
                   value="{{ _qs.date or '' }}">
          </div>
          {% else %}
          <input type="hidden" name="date" value="{{ _qs.date or '' }}">
          {% endif %}'''

assert old_ad in s, "activity date group not found"
s = s.replace(old_ad, new_ad, 1)

# 5. Travellers group
old_trav = '''        {# ── Travellers ──────────────────────────────────────────── #}
        <div class="eltut-filters-group">
          <label class="eltut-filters-label">
            <i class="bi bi-people-fill"></i> Travellers
          </label>
          <div class="row g-2">
            <div class="col-6">
              <div class="eltut-filters-stepper">
                <span class="eltut-filters-step-label">Adults</span>
                <div class="eltut-filters-step-controls">
                  <button type="button" class="eltut-filters-step-btn" data-step="-1" data-target="ef-adults">−</button>
                  <input type="number" name="adults" id="ef-adults" class="eltut-filters-step-input"
                         value="{{ _qs.adults or 1 }}" min="1" max="8">
                  <button type="button" class="eltut-filters-step-btn" data-step="1" data-target="ef-adults">+</button>
                </div>
              </div>
            </div>
            <div class="col-6">
              <div class="eltut-filters-stepper">
                <span class="eltut-filters-step-label">Children</span>
                <div class="eltut-filters-step-controls">
                  <button type="button" class="eltut-filters-step-btn" data-step="-1" data-target="ef-children">−</button>
                  <input type="number" name="children" id="ef-children" class="eltut-filters-step-input"
                         value="{{ _qs.children or 0 }}" min="0" max="8">
                  <button type="button" class="eltut-filters-step-btn" data-step="1" data-target="ef-children">+</button>
                </div>
              </div>
            </div>
          </div>
        </div>'''

new_trav = '''        {# ── Travellers (hidden when widget at top handles it) ───── #}
        {% if not compact %}
        <div class="eltut-filters-group">
          <label class="eltut-filters-label">
            <i class="bi bi-people-fill"></i> Travellers
          </label>
          <div class="row g-2">
            <div class="col-6">
              <div class="eltut-filters-stepper">
                <span class="eltut-filters-step-label">Adults</span>
                <div class="eltut-filters-step-controls">
                  <button type="button" class="eltut-filters-step-btn" data-step="-1" data-target="ef-adults">−</button>
                  <input type="number" name="adults" id="ef-adults" class="eltut-filters-step-input"
                         value="{{ _qs.adults or 1 }}" min="1" max="8">
                  <button type="button" class="eltut-filters-step-btn" data-step="1" data-target="ef-adults">+</button>
                </div>
              </div>
            </div>
            <div class="col-6">
              <div class="eltut-filters-stepper">
                <span class="eltut-filters-step-label">Children</span>
                <div class="eltut-filters-step-controls">
                  <button type="button" class="eltut-filters-step-btn" data-step="-1" data-target="ef-children">−</button>
                  <input type="number" name="children" id="ef-children" class="eltut-filters-step-input"
                         value="{{ _qs.children or 0 }}" min="0" max="8">
                  <button type="button" class="eltut-filters-step-btn" data-step="1" data-target="ef-children">+</button>
                </div>
              </div>
            </div>
          </div>
        </div>
        {% else %}
        <input type="hidden" name="adults" value="{{ _qs.adults or 1 }}">
        <input type="hidden" name="children" value="{{ _qs.children or 0 }}">
        {% endif %}'''

assert old_trav in s, "travellers group not found"
s = s.replace(old_trav, new_trav, 1)

open(path, "w", encoding="utf-8").write(s)
print("partial updated with compact mode")