path = "templates/public/_search_widget.html"
s = open(path, "r", encoding="utf-8").read()

# Add package-specific destinations set at the top
old_header = "{% set _dests = search_destinations() %}"
new_header = "{% set _dests = search_destinations() %}\n{% set _pkg_dests = search_package_destinations() %}"
assert old_header in s, "widget header anchor not found"
s = s.replace(old_header, new_header, 1)

# The package tab pane starts at id="sw-package". Find that section
# and swap the destinations loop from _dests to _pkg_dests.
# The package pane lives between id="sw-package" and id="sw-activity".
start = s.find('id="sw-package"')
end = s.find('id="sw-activity"')
assert start > 0 and end > start, "package pane boundaries not found"

segment = s[start:end]
# Replace all {% for ... in _dests %} within that segment with _pkg_dests
segment_new = segment.replace("in _dests", "in _pkg_dests")
segment_new = segment.replace("_dests|", "_pkg_dests|")

s = s[:start] + segment_new + s[end:]
open(path, "w", encoding="utf-8").write(s)
print("widget patched — package tab now uses search_package_destinations()")