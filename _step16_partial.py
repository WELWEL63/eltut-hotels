path = "templates/public/_filters_sidebar.html"
s = open(path, "r", encoding="utf-8").read()

old = '''{% set _pt = product_type %}
{% set _qs = qs %}

<aside class="col-lg-3">'''
new = '''{% set _pt = product_type %}
{% set _qs = qs %}

<aside class="{% if wrapper_class %}{{ wrapper_class }}{% else %}col-lg-3{% endif %}">'''
assert old in s, "aside anchor not found"
s = s.replace(old, new, 1)

# Add min-width to the shell so grid columns never squash it
old_shell = '''.eltut-filters-shell { position: sticky; top: 1rem; }'''
new_shell = '''.eltut-filters-shell {
  position: sticky; top: 1rem;
  min-width: 0;
  width: 100%;
}'''
assert old_shell in s, "shell css not found"
s = s.replace(old_shell, new_shell, 1)

open(path, "w", encoding="utf-8").write(s)
print("partial updated: wrapper_class support + min-width")