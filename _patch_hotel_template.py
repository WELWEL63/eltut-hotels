path = "templates/public/booking_confirmation.html"
s = open(path, "r", encoding="utf-8").read()

# 1. Add room block inside hotel_obj block (after description)
anchor = '''            {% if hotel_obj.description %}
              <p class="text-muted mb-0" style="font-size:0.95rem;">{{ hotel_obj.description[:300] }}{% if hotel_obj.description|length > 300 %}…{% endif %}</p>
            {% endif %}
          </div>
        </div>'''
replacement = '''            {% if hotel_obj.description %}
              <p class="text-muted mb-0" style="font-size:0.95rem;">{{ hotel_obj.description[:300] }}{% if hotel_obj.description|length > 300 %}…{% endif %}</p>
            {% endif %}
            {% if hotel_room_obj %}
            <div class="mt-3 pt-3" style="border-top:1px dashed rgba(0,0,0,0.1);">
              <div class="text-muted small text-uppercase mb-1" style="letter-spacing:.06em;">Your room</div>
              <div class="fw-semibold">{{ hotel_room_obj.type }}</div>
              {% if hotel_room_obj.meal_plan %}
                <div class="small text-muted"><i class="bi bi-egg-fried"></i> {{ hotel_room_obj.meal_plan|replace("_", " ")|title }}</div>
              {% endif %}
              {% if hotel_room_obj.max_occupancy %}
                <div class="small text-muted"><i class="bi bi-people"></i> Up to {{ hotel_room_obj.max_occupancy }} guests</div>
              {% endif %}
            </div>
            {% endif %}
          </div>
        </div>'''
assert anchor in s, "hotel description anchor not found"
s = s.replace(anchor, replacement, 1)

# 2. Fix price-breakdown fallback label: hotel bookings should say "Hotel stay" with room info
old_fallback = '''              <div class="d-flex justify-content-between small mb-2">
                <span class="text-muted">
                  {% if booking.product_type == 'hotel' %}Hotel stay
                  {% elif booking.product_type == 'activity' %}Activity
                  {% else %}Package{% endif %}
                </span>
                <span>{{ booking.currency }} {{ "%.2f"|format(booking.total_amount - addon_total) }}</span>
              </div>'''
new_fallback = '''              <div class="d-flex justify-content-between small mb-2">
                <span class="text-muted">
                  {% if booking.product_type == 'hotel' %}
                    {% if hotel_obj %}{{ hotel_obj.name }}{% else %}Hotel stay{% endif %}
                    {% if hotel_room_obj %} — {{ hotel_room_obj.type }}{% endif %}
                  {% elif booking.product_type == 'activity' %}
                    {% if activity_obj %}{{ activity_obj.name }}{% else %}Activity{% endif %}
                  {% else %}Package{% endif %}
                </span>
                <span>{{ booking.currency }} {{ "%.2f"|format(booking.total_amount - addon_total) }}</span>
              </div>'''
assert old_fallback in s, "price fallback label block not found"
s = s.replace(old_fallback, new_fallback, 1)

# 3. Fix add-ons header — should not show when there are no addon_items (already guarded), OK.
#    But "Package subtotal" in the pricing_breakdown branch is fine — only used for packages.

open(path, "w", encoding="utf-8").write(s)
print("template labels + room details patched")