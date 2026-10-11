from app import create_app
from services import search_service

app = create_app()
with app.app_context():
    for ptype in ('activity', 'hotel', 'package'):
        r = search_service.search(product_type=ptype, destination='hurghada', per_page=1)
        if r['items']:
            item = r['items'][0]
            print(f"{ptype:10} currency={item.get('currency')!r} price_adult={item.get('price_adult')}")
        else:
            print(f"{ptype:10} no results")
