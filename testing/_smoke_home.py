from app import create_app

app = create_app()
with app.test_client() as client:
    r = client.get("/")
    print(f"Home status: {r.status_code}")
    html = r.get_data(as_text=True)
    for word in ["Great value", "Affordable", "Top experiences", "Popular destinations"]:
        print(f"  {word!r} in HTML: {word in html}")
