path = "templates/public/package_list.html"
lines = open(path, "r", encoding="utf-8").read().splitlines(keepends=True)

start = None
end = None
for i, ln in enumerate(lines):
    if "{# ─── Filter sidebar ─── #}" in ln and start is None:
        start = i
    if start is not None and "</aside>" in ln and i > start:
        end = i
        break

assert start is not None and end is not None, f"sidebar bounds not found: {start} {end}"

new_block = '''            {# ─── Shared filter sidebar ─── #}
            {% set qs = {
                "destination": selected_destination.slug if selected_destination else "",
                "check_in": request.args.get("check_in") or "",
                "check_out": request.args.get("check_out") or "",
                "adults": request.args.get("adults") or 2,
                "children": request.args.get("children") or 0,
                "q": query_text or "",
            } %}
            {% set product_type = "package" %}
            {% set url_for_endpoint = "public.package_list" %}
            {% set clear_url = url_for("public.package_list") %}
            {% set package_destinations = search_package_destinations() %}
            {% include "public/_filters_sidebar.html" %}
'''

lines[start:end+1] = [new_block]
open(path, "w", encoding="utf-8").writelines(lines)
print(f"package_list.html patched (replaced lines {start+1}-{end+1})")