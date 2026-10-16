# -*- coding: utf-8 -*-
"""Add Edit button + inline edit form to room_form.html rates table."""
import io
path = "templates/admin/room_form.html"

with io.open(path, encoding="utf-8") as f:
    c = f.read()

# The current tr block (exact text from user paste)
old_tr = '''{% for r in rates %}
                        <tr>
                            <td>{{ r.valid_from.strftime("%d %b %Y") if r.valid_from else "—"}}</td>
                            <td>{{ r.valid_to.strftime("%d %b %Y") if r.valid_to else "—" }}</td>
                            <td>{{ "%.2f"|format(r.adult_price) }}</td>
                            <td>{{ "%.2f"|format(r.child_price) }}</td>
                            <td>{{ r.currency }}</td>
                            <td class="text-end">
                                <form method="POST" class="d-inline"
                                      action="{{ url_for('admin.room_rate_delete', rate_id=r.id) }}"
                                      onsubmit="return confirm('Delete this rate window?');">
                                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                                    <button class="btn btn-sm btn-outline-danger">Delete</button>
                                </form>
                            </td>
                        </tr>
                    {% endfor %}'''

new_tr = '''{% for r in rates %}
                        <tr>
                            <td>{{ r.valid_from.strftime("%d %b %Y") if r.valid_from else "—"}}</td>
                            <td>{{ r.valid_to.strftime("%d %b %Y") if r.valid_to else "—" }}</td>
                            <td class="text-end">{{ "%.2f"|format(r.adult_price) }}</td>
                            <td class="text-end">{{ "%.2f"|format(r.child_price) }}</td>
                            <td>{{ r.currency }}</td>
                            <td class="text-end">
                                <button type="button" class="btn btn-sm btn-outline-primary"
                                        data-bs-toggle="collapse"
                                        data-bs-target="#rate-edit-{{ r.id }}">
                                    Edit
                                </button>
                                <form method="POST" class="d-inline"
                                      action="{{ url_for('admin.room_rate_delete', rate_id=r.id) }}"
                                      onsubmit="return confirm('Delete this rate window?');">
                                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                                    <button class="btn btn-sm btn-outline-danger">Delete</button>
                                </form>
                            </td>
                        </tr>
                        <tr class="collapse" id="rate-edit-{{ r.id }}">
                            <td colspan="6" class="bg-light">
                                <form method="POST"
                                      action="{{ url_for('admin.room_rate_edit', rate_id=r.id) }}"
                                      class="row g-2 align-items-end p-2">
                                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                                    <div class="col-md-2">
                                        <label class="form-label small mb-1">Valid from</label>
                                        <input type="date" name="valid_from" class="form-control form-control-sm"
                                               value="{{ r.valid_from.isoformat() if r.valid_from else '' }}">
                                    </div>
                                    <div class="col-md-2">
                                        <label class="form-label small mb-1">Valid to</label>
                                        <input type="date" name="valid_to" class="form-control form-control-sm"
                                               value="{{ r.valid_to.isoformat() if r.valid_to else '' }}">
                                    </div>
                                    <div class="col-md-2">
                                        <label class="form-label small mb-1">Adult price</label>
                                        <input type="number" step="0.01" min="0" name="adult_price"
                                               class="form-control form-control-sm"
                                               value="{{ '%.2f'|format(r.adult_price) }}">
                                    </div>
                                    <div class="col-md-2">
                                        <label class="form-label small mb-1">Child price</label>
                                        <input type="number" step="0.01" min="0" name="child_price"
                                               class="form-control form-control-sm"
                                               value="{{ '%.2f'|format(r.child_price) }}">
                                    </div>
                                    <div class="col-md-2">
                                        <label class="form-label small mb-1">Currency</label>
                                        <select name="currency" class="form-select form-select-sm">
                                            {% for cur in ["GBP", "EUR", "USD", "EGP"] %}
                                                <option value="{{ cur }}"
                                                    {% if r.currency == cur %}selected{% endif %}>{{ cur }}</option>
                                            {% endfor %}
                                        </select>
                                    </div>
                                    <div class="col-md-2 d-flex gap-2">
                                        <button class="btn btn-primary btn-sm flex-grow-1">
                                            <i class="bi bi-check2"></i> Save
                                        </button>
                                    </div>
                                </form>
                            </td>
                        </tr>
                    {% endfor %}'''

if old_tr in c:
    c = c.replace(old_tr, new_tr, 1)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("Edit button + inline form added")
else:
    print("Anchor not found — trying without exact whitespace")
    # Alternative: use a looser anchor
    idx = c.find("{% for r in rates %}")
    if idx > 0:
        print("Found 'for r in rates' at", idx)
        print("First 200 chars after:", repr(c[idx:idx+200]))