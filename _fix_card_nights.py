# -*- coding: utf-8 -*-
"""Add Nights column to flight cards table in admin package form."""
import io
path = "templates/admin/package_form.html"
with io.open(path, encoding="utf-8") as f:
    c = f.read()

# The flight cards table header
old_head = '''<tr>
                            <th>#</th>
                            <th>Outbound</th>
                            <th>Inbound</th>
                            <th>Label</th>
                            <th>Active</th>
                            <th class="text-end">Actions</th>
                        </tr>'''

new_head = '''<tr>
                            <th>#</th>
                            <th>Outbound</th>
                            <th>Inbound</th>
                            <th class="text-center">Nights</th>
                            <th>Label</th>
                            <th>Active</th>
                            <th class="text-end">Actions</th>
                        </tr>'''

if old_head in c:
    c = c.replace(old_head, new_head, 1)
    print("Header updated")
else:
    print("Header anchor not found")

# The flight card body cell - insert nights after Inbound td
old_body = '''<td class="small">
                                    {% if c.inbound_flight %}
                                        {{ c.inbound_flight.airline }}<br>
                                        {{ c.inbound_flight.origin }} - {{ c.inbound_flight.destination }}<br>
                                        <span class="text-muted">{{ c.inbound_flight.departure_date }} · GBP {{ "%.2f"|format(c.inbound_flight.price_gbp) }}</span>
                                    {% else %}<span class="text-muted">-</span>{% endif %}
                                </td>
                                <td class="small">{{ c.label or c.display_label }}</td>'''

new_body = '''<td class="small">
                                    {% if c.inbound_flight %}
                                        {{ c.inbound_flight.airline }}<br>
                                        {{ c.inbound_flight.origin }} - {{ c.inbound_flight.destination }}<br>
                                        <span class="text-muted">{{ c.inbound_flight.departure_date }} · GBP {{ "%.2f"|format(c.inbound_flight.price_gbp) }}</span>
                                    {% else %}<span class="text-muted">-</span>{% endif %}
                                </td>
                                <td class="text-center">
                                    {% if c.outbound_flight and c.inbound_flight %}
                                        {% set n = (c.inbound_flight.departure_date - c.outbound_flight.departure_date).days %}
                                        {% if n > 0 %}
                                            <span class="badge bg-primary">{{ n }}</span>
                                        {% else %}
                                            <span class="badge bg-danger">{{ n }}</span>
                                        {% endif %}
                                    {% else %}
                                        <span class="text-muted">-</span>
                                    {% endif %}
                                </td>
                                <td class="small">{{ c.label or c.display_label }}</td>'''

if old_body in c:
    c = c.replace(old_body, new_body, 1)
    print("Body row updated")
else:
    print("Body anchor not found - trying alternative")
    # Try without the exact whitespace
    idx = c.find('{{ c.inbound_flight.origin }} - {{ c.inbound_flight.destination }}')
    if idx > 0:
        print("Found similar body at:", idx)

with io.open(path, "w", encoding="utf-8") as f:
    f.write(c)