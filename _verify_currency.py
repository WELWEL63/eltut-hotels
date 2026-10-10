from app import create_app
from services import search_service

app = create_app()
with app.app_context():
    r = search_service.search(product_type='activity', destination='hurghada', per_page=3)
    print(f"total: {r['total']}")
    for item in r['items'][:3]:
        print(f"  {item['name'][:40]!r} currency={item['currency']!r} price={item['price_adult']}")
