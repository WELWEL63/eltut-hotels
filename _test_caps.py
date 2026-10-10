from app import create_app

app = create_app()
client = app.test_client()

print("=" * 60)
print("FUNCTIONAL TEST: party-size cap + hotel room filter")
print("=" * 60)

# Test 1: normal values should return many hotels
r = client.get("/search/results?type=hotel&destination=hurghada&check_in=2027-01-28&check_out=2027-02-04&adults=2&children=2")
html = r.get_data(as_text=True)
has_empty = "No matches found" in html
print(f"[TEST 1] adults=2 children=2 (party=4)")
print(f"         status={r.status_code}")
print(f"         result={'EMPTY STATE' if has_empty else 'shows hotels'}")

# Test 2: 999/999 should return EMPTY STATE
r = client.get("/search/results?type=hotel&destination=hurghada&check_in=2027-01-28&check_out=2027-02-04&adults=999&children=999")
html = r.get_data(as_text=True)
has_empty = "No matches found" in html
print(f"[TEST 2] adults=999 children=999")
print(f"         status={r.status_code}")
print(f"         result={'EMPTY STATE (correct!)' if has_empty else 'shows hotels (WRONG)'}")

# Test 3: party=5 should return EMPTY STATE (no room holds 5)
r = client.get("/search/results?type=hotel&destination=hurghada&check_in=2027-01-28&check_out=2027-02-04&adults=5&children=0")
html = r.get_data(as_text=True)
has_empty = "No matches found" in html
print(f"[TEST 3] adults=5 children=0 (party=5)")
print(f"         status={r.status_code}")
print(f"         result={'EMPTY STATE (correct!)' if has_empty else 'shows hotels (WRONG)'}")

# Test 4: party=4 should still work
r = client.get("/search/results?type=hotel&destination=hurghada&check_in=2027-01-28&check_out=2027-02-04&adults=4&children=0")
html = r.get_data(as_text=True)
has_empty = "No matches found" in html
print(f"[TEST 4] adults=4 children=0 (party=4)")
print(f"         status={r.status_code}")
print(f"         result={'shows hotels (correct!)' if not has_empty else 'EMPTY STATE (WRONG)'}")
