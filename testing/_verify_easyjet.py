from app import create_app

app = create_app()
with app.test_client() as client:
    r = client.get("/packages/amzing-redsea-pkg-0360-2?check_in=2027-01-28&check_out=2027-02-04&adults=2&children=2")
    html = r.get_data(as_text=True)
    # Check both spellings
    for label in ["EasyJet", "easy jet", "easyjet"]:
        print(f"  {label!r} present: {label in html}")
