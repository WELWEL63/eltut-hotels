path = "templates/admin/flight_admin.html"
s = open(path, "r", encoding="utf-8").read()

old = """    <div class="d-flex gap-2">
        <a href="{{ url_for('admin.flight_admin_import') }}" class="btn btn-primary">
            <i class="bi bi-upload"></i> Upload CSV
        </a>
        <a href="{{ url_for('admin.flight_admin_export') }}" class="btn btn-outline-primary">
            <i class="bi bi-download"></i> Download CSV
        </a>
    </div>"""

new = """    <div class="d-flex gap-2">
        <a href="{{ url_for('admin.flight_admin_import') }}" class="btn btn-primary">
            <i class="bi bi-upload"></i> Upload CSV
        </a>
        <a href="{{ url_for('admin.flight_admin_export') }}" class="btn btn-outline-primary">
            <i class="bi bi-download"></i> Download CSV
        </a>

        {% if total > 0 %}
        <button type="button" class="btn btn-outline-danger"
                data-bs-toggle="modal" data-bs-target="#deleteAllFlightsModal">
            <i class="bi bi-trash3"></i> Delete all
        </button>
        {% endif %}
    </div>"""

assert old in s, "button block not found"
s = s.replace(old, new, 1)

modal = """
{# ═══════════════════════════════════════════════════════════════════
   DELETE ALL FLIGHTS — confirmation modal
   ═══════════════════════════════════════════════════════════════════ #}
{% if total > 0 %}
<div class="modal fade" id="deleteAllFlightsModal" tabindex="-1">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
            <form method="POST" action="{{ url_for('admin.flight_admin_delete_all') }}">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <input type="hidden" name="confirm_delete_all" value="yes">

                <div class="modal-header border-0">
                    <h5 class="modal-title text-danger">
                        <i class="bi bi-exclamation-triangle-fill"></i>
                        Delete ALL flight prices?
                    </h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>

                <div class="modal-body">
                    <p class="mb-2">
                        This will permanently delete <strong>{{ total }}</strong>
                        flight price rows.
                    </p>
                    <p class="mb-0 text-muted small">
                        This cannot be undone. Use it only when you intend to
                        import a completely fresh CSV.
                    </p>
                </div>

                <div class="modal-footer border-0">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                        Cancel
                    </button>
                    <button type="submit" class="btn btn-danger">
                        <i class="bi bi-trash3"></i> Yes, delete everything
                    </button>
                </div>
            </form>
        </div>
    </div>
</div>
{% endif %}
"""

end_marker = "{% endblock %}"
assert end_marker in s
s = s.replace(end_marker, modal + "\n" + end_marker, 1)

open(path, "w", encoding="utf-8").write(s)
print("flight_admin.html patched: delete-all button + modal")
