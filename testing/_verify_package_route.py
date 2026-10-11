from app import create_app
from blueprints.public.package_routes import package_detail
import inspect

app = create_app()
# Just confirm import works — actual test via browser later
print("package_detail function loads:", callable(package_detail))
