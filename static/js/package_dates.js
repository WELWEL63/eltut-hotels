/**
 * Package Details Page - Dynamic Date Sync
 * Updates the sidebar dates when a flight card is selected.
 */
document.addEventListener("DOMContentLoaded", function() {
    console.log("[ElTut] Package dates script loaded");

    function syncDates(card) {
        if (!card) return;

        const dep = card.getAttribute('data-departure');
        const ret = card.getAttribute('data-return');

        console.log("[ElTut] Card clicked - departure:", dep, "return:", ret);

        if (!dep || !ret) {
            console.warn("[ElTut] Missing data-departure or data-return");
            return;
        }

        // Parse ISO dates (YYYY-MM-DD)
        const formatDate = (isoStr) => {
            const parts = isoStr.split('-');
            if (parts.length !== 3) return isoStr;
            const d = new Date(parts[0], parts[1] - 1, parts[2]);
            return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
        };

        const d1 = new Date(dep);
        const d2 = new Date(ret);
        const nights = Math.round((d2 - d1) / (1000 * 60 * 60 * 24));

        const dateEl = document.getElementById('sidebar-dates');
        const nightsEl = document.getElementById('sidebar-nights');

        if (dateEl) {
            dateEl.innerHTML = '<i class="bi bi-calendar-range text-eltut-terracotta"></i> <strong>' + formatDate(dep) + '</strong> → <strong>' + formatDate(ret) + '</strong>';
            console.log("[ElTut] Updated sidebar dates");
        } else {
            console.warn("[ElTut] #sidebar-dates not found");
        }

        if (nightsEl) {
            nightsEl.innerHTML = '<i class="bi bi-moon-stars"></i> ' + nights + ' nights';
            console.log("[ElTut] Updated sidebar nights to:", nights);
        }
    }

    // Attach listener to radio inputs
    const radios = document.querySelectorAll('input[name="package_flight_id"]');
    console.log("[ElTut] Found", radios.length, "radio inputs");

    radios.forEach(radio => {
        radio.addEventListener('change', function() {
            const card = this.closest('[data-departure]');
            syncDates(card);
        });
    });

    // Also listen for clicks on the whole card (in case radio is not the target)
    const cards = document.querySelectorAll('[data-departure][data-return]');
    console.log("[ElTut] Found", cards.length, "flight cards");

    cards.forEach(card => {
        card.addEventListener('click', function() {
            syncDates(this);
        });
    });

    // Sync on page load if a radio is already checked
    const checked = document.querySelector('input[name="package_flight_id"]:checked');
    if (checked) {
        const card = checked.closest('[data-departure]');
        syncDates(card);
    }
});
