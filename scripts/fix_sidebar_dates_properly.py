import re

file_path = "templates/public/package_detail.html"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Remove the misplaced script from title
content = content.replace(
    '{% block title %}{{ package.name }} — {{ config.APP_NAME }}<script src="/static/js/package_dates.js"></script>',
    '{% block title %}{{ package.name }} — {{ config.APP_NAME }}'
)

# 2. Find the selectOption function's "Update price breakdown" section
# and inject the sidebar-dates update BEFORE it
old_marker = '''        // ─── Update price breakdown ──────────────────────────────'''

new_marker = '''        // ─── Update sidebar dates & nights ───────────────────────
        const sidebarDatesEl = document.getElementById('sidebar-dates');
        const sidebarNightsEl = document.querySelector('#sidebar-dates + .small');
        if (sidebarDatesEl && dep && ret) {
            const fmtDate = (isoStr) => {
                const parts = isoStr.split('-');
                if (parts.length !== 3) return isoStr;
                const d = new Date(parts[0], parts[1] - 1, parts[2]);
                return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
            };
            sidebarDatesEl.innerHTML = '<i class="bi bi-calendar-range text-eltut-terracotta"></i> <strong>' + fmtDate(dep) + '</strong> → <strong>' + fmtDate(ret) + '</strong>';
            
            // Update the nights line that comes right after
            const nightsLine = sidebarDatesEl.parentElement.nextElementSibling;
            if (nightsLine && nightsLine.classList.contains('small')) {
                const d1 = new Date(dep);
                const d2 = new Date(ret);
                const nightsCount = Math.round((d2 - d1) / (1000 * 60 * 60 * 24));
                nightsLine.innerHTML = '<i class="bi bi-moon-stars"></i> ' + nightsCount + ' night' + (nightsCount === 1 ? '' : 's') + ' &middot; <i class="bi bi-people"></i> ' + ADULTS + ' adult' + (ADULTS === 1 ? '' : 's') + (CHILDREN > 0 ? ' + ' + CHILDREN + ' child' + (CHILDREN === 1 ? '' : 'ren') : '');
            }
        }

        // ─── Update price breakdown ──────────────────────────────'''

if old_marker in content:
    content = content.replace(old_marker, new_marker, 1)
    print("✅ Injected sidebar dates update into selectOption()")
else:
    print("❌ Could not find the marker. Check the file manually.")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("\nDone.")
print("Next:")
print("1. Restart Flask (CTRL+C then python app.py)")
print("2. Hard refresh (CTRL+F5)")
print("3. Click a flight card - sidebar dates should update instantly")
