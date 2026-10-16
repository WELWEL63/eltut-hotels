path = "templates/public/search_results.html"
s = open(path, "r", encoding="utf-8").read()

old = '''            {% set wrapper_class = "sr-sidebar" %}
            {% include "public/_filters_sidebar.html" %}'''
new = '''            {% set wrapper_class = "sr-sidebar" %}
            {% set compact = True %}
            {% include "public/_filters_sidebar.html" %}'''

assert old in s, "search_results include not found"
s = s.replace(old, new, 1)
open(path, "w", encoding="utf-8").write(s)
print("search_results now passes compact=True")