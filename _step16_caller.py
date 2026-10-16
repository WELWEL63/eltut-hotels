path = "templates/public/search_results.html"
s = open(path, "r", encoding="utf-8").read()

old = '''            {% set clear_url = url_for("public.search_results", type=result['product_type']) %}
            {% include "public/_filters_sidebar.html" %}'''
new = '''            {% set clear_url = url_for("public.search_results", type=result['product_type']) %}
            {% set wrapper_class = "sr-sidebar" %}
            {% include "public/_filters_sidebar.html" %}'''

assert old in s, "search_results include anchor not found"
s = s.replace(old, new, 1)
open(path, "w", encoding="utf-8").write(s)
print("search_results passes wrapper_class='sr-sidebar'")