path = "templates/public/hotel_detail.html"
s = open(path, "r", encoding="utf-8").read()

old = '''                            <div class="text-muted small" id="sidebar-price-label">From</div>
                            <div class="fs-3 fw-bold text-eltut-terracotta">
                                &euro;<span id="sidebar-total-value">{{ "%.2f"|format(cheapest_total) }}</span>
                                <small class="text-muted fw-normal fs-6">total</small>
                            </div>'''

new = '''                            <div class="text-muted small mb-2" id="sidebar-room-summary">
                                <i class="bi bi-door-open"></i>
                                <span id="sidebar-room-name">—</span>
                                <span class="mx-1">&middot;</span>
                                <i class="bi bi-egg-fried"></i>
                                <span id="sidebar-meal-plan">—</span>
                            </div>
                            <div class="text-muted small" id="sidebar-price-label">From</div>
                            <div class="fs-3 fw-bold text-eltut-terracotta">
                                &euro;<span id="sidebar-total-value">{{ "%.2f"|format(cheapest_total) }}</span>
                                <small class="text-muted fw-normal fs-6">total</small>
                            </div>'''

assert old in s, "sidebar price block not found"
s = s.replace(old, new, 1)

# Also update the JS to populate room name + meal plan when a room is selected
old_js = '''            updateSidebar(card.dataset.total, card.dataset.perNight, 'Selected');'''
new_js = '''            updateSidebar(card.dataset.total, card.dataset.perNight, 'Selected');
            // Also show the selected room name + meal plan in the sidebar
            const roomNameEl = document.getElementById('sidebar-room-name');
            const mealPlanEl = document.getElementById('sidebar-meal-plan');
            if (roomNameEl) roomNameEl.textContent = card.dataset.roomName || '—';
            if (mealPlanEl) mealPlanEl.textContent = card.dataset.mealPlan || '—';'''

assert old_js in s, "updateSidebar call not found"
s = s.replace(old_js, new_js, 1)

# And ensure the room cards expose data-meal-plan
old_card = '''                             data-room-name="{{ room.type }}"'''
new_card = '''                             data-room-name="{{ room.type }}"
                             data-meal-plan="{{ (room.meal_plan or '')|replace('_', ' ')|title }}"'''

assert old_card in s, "room card data-room-name anchor not found"
s = s.replace(old_card, new_card, 1)

open(path, "w", encoding="utf-8").write(s)
print("hotel_detail.html patched: sidebar shows room name + meal plan")