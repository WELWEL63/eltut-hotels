path = "templates/public/search_results.html"
lines = open(path, "r", encoding="utf-8").read().splitlines(keepends=True)

# Find the aside with class "sr-sidebar"
start = None
end = None
for i, ln in enumerate(lines):
    if 'class="sr-sidebar"' in ln and start is None:
        start = i
        # back up to include the comment line above
        if i > 0 and "Sidebar filters" in lines[i-1]:
            start = i - 1
    if start is not None and "</aside>" in ln and i > start:
        end = i
        break

assert start is not None and end is not None, f"sidebar bounds not found: {start} {end}"

new_block = '''            {# ──────────────── Shared filter sidebar ──────────────── #}
            {% if result['product_type'] == 'package' %}
                {% set _dest_list = package_destinations %}
            {% else %}
                {% set _dest_list = destinations %}
            {% endif %}
            {% set qs = {
                "destination": result['filters']['destination'] or "",
                "check_in": result['filters']['check_in'] or "",
                "check_out": result['filters']['check_out'] or "",
                "date": result['filters']['activity_date'] or "",
                "adults": result['filters']['adults'],
                "children": result['filters']['children'],
                "q": result['filters']['q'] or "",
            } %}
            {% set destinations = _dest_list %}
            {% set product_type = result['product_type'] %}
            {% set url_for_endpoint = "public.search_results" %}
            {% set sort = result['filters']['sort'] %}
            {% set query_text = result['filters']['q'] or "" %}
            {% set clear_url = url_for("public.search_results", type=result['product_type']) %}
            {% include "public/_filters_sidebar.html" %}
'''

lines[start:end+1] = [new_block]
open(path, "w", encoding="utf-8").writelines(lines)
print(f"search_results.html sidebar patched (replaced lines {start+1}-{end+1})")