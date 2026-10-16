from app import create_app
from services import search_service

app = create_app()
ctx = app.app_context()
ctx.push()
print("Widget dropdown destinations (only those with active packages):")
for d in search_service.destinations_for_widget():
    print(f"  {d['slug']:24} {d['name']}")
ctx.pop()