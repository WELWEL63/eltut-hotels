path = "blueprints/public/package_routes.py"
s = open(path, "r", encoding="utf-8").read()

# Replace the destinations list in package_list with the package-only list.
old = '''    destinations = list(db.session.scalars(
        select(Destination).order_by(Destination.name)
    ))

    return render_template(
        "public/package_list.html",'''

new = '''    from services.search_service import destinations_for_package_widget
    destinations = destinations_for_package_widget()

    return render_template(
        "public/package_list.html",'''

assert old in s, "package_list destinations block not found"
s = s.replace(old, new, 1)
open(path, "w", encoding="utf-8").write(s)
print("package_routes.py: destinations filtered to package-only")