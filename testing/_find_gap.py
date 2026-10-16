from app import create_app
import re

app = create_app()
client = app.test_client()
r = client.get("/")
html = r.get_data(as_text=True)

# Find <main> and the first 800 characters after it
main_idx = html.find("<main>")
if main_idx == -1:
    print("No <main> found")
    raise SystemExit(1)

after_main = html[main_idx:main_idx + 1500]
print("=" * 70)
print("CONTENT AFTER <main> (first 1500 chars):")
print("=" * 70)
print(after_main)
print()
print("=" * 70)
print("SEARCH FOR SUSPECT CLASSES in the whole page:")
print("=" * 70)
for pat in ["py-4", "pt-4", "mt-3", "mt-4", "my-4", "py-5", "py-3",
            "hero-eltut", "slideshow", "carousel", "spacer", "empty"]:
    count = len(re.findall(re.escape(pat), html))
    if count:
        print(f"  '{pat}' appears {count} time(s)")

# Print the first occurrence context for each suspect
print()
print("=" * 70)
print("CONTEXT — first occurrence of each suspect class:")
print("=" * 70)
for pat in ["hero-eltut", "slideshow", "carousel", "py-4", "pt-4", "mt-3", "mt-4"]:
    idx = html.find(pat)
    if idx == -1:
        continue
    start = max(0, idx - 120)
    end = min(len(html), idx + 120)
    snippet = html[start:end].replace("\n", "\\n").replace("\r", "")
    print(f"\n--- {pat} ---")
    print(snippet)
