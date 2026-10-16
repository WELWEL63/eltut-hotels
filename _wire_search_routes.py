path = "blueprints/public/search_routes.py"
s = open(path, "r", encoding="utf-8").read()

old = '''    # ─── Dropdown data for the persistent widget on the results page ─
    destinations = search_service.destinations_for_widget()

    return render_template(
        "public/search_results.html",
        result=result,
        destinations=destinations,'''

new = '''    # ─── Dropdown data for the widget + filter sidebar ─
    destinations = search_service.destinations_for_widget()
    package_destinations = search_service.destinations_for_package_widget()

    return render_template(
        "public/search_results.html",
        result=result,
        destinations=destinations,
        package_destinations=package_destinations,'''

assert old in s, "search_routes dropdown block not found"
s = s.replace(old, new, 1)
open(path, "w", encoding="utf-8").write(s)
print("search_routes.py patched")