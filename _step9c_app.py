path = "app.py"
s = open(path, "r", encoding="utf-8").read()

old = '''    app.jinja_env.globals["search_destinations"] = _search_destinations'''

new = '''    app.jinja_env.globals["search_destinations"] = _search_destinations

    # Same idea, but only destinations that have at least one active
    # package. Used by the Packages tab of the search widget so
    # customers only see destinations they can actually book.
    def _search_package_destinations():
        try:
            from flask import g
            cached = getattr(g, "_search_pkg_destinations_cache", None)
            if cached is not None:
                return cached
            from services import search_service
            dests = search_service.destinations_for_package_widget()
            g._search_pkg_destinations_cache = dests
            return dests
        except Exception:
            return []

    app.jinja_env.globals["search_package_destinations"] = _search_package_destinations'''

assert old in s, "search_destinations registration not found"
s = s.replace(old, new, 1)
open(path, "w", encoding="utf-8").write(s)
print("app.py patched with search_package_destinations")