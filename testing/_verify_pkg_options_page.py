from app import create_app

app = create_app()
with app.test_client() as client:
    r = client.get("/packages/amzing-redsea-pkg-0360-2?check_in=2027-01-28&check_out=2027-02-04&adults=2&children=2")
    html = r.get_data(as_text=True)
    print(f"Status: {r.status_code}")
    for label in ["EasyJet", "TUI", "Wizz Air", "888", "989", "1050"]:
        print(f"  {label!r} present: {label in html}")
