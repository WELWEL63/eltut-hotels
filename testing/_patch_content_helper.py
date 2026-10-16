p = 'services/content_service.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# Append the destination-image helper near the end (before __all__ if it exists)
helper_code = '''

# ─── Destination images (home page) ──────────────────────────────
# Each destination has a hero image stored under a content key:
#     destination_image_<slug>
# If missing, falls back to "destination_image_default".
# Admin manages these at /admin/content/edit/destination_image_<slug>
def destination_image(slug: str | None, fallback: str | None = None) -> str | None:
    """Return the image URL for a destination slug, or None."""
    if not slug:
        return fallback or get("destination_image_default", None)
    value = get(f"destination_image_{slug}", None)
    if value:
        return value
    if fallback:
        return fallback
    return get("destination_image_default", None)


def all_destination_images() -> dict[str, str]:
    """Return {slug: image_url} for every destination_image_* key that has a value."""
    values = all_values()
    prefix = "destination_image_"
    out: dict[str, str] = {}
    for k, v in values.items():
        if not k.startswith(prefix):
            continue
        suffix = k[len(prefix):]
        if suffix == "default":
            continue
        if v:
            out[suffix] = v
    return out
'''

# Insert before the final __all__ if present, else append
anchor = "\n__all__ = "
if anchor in c:
    c = c.replace(anchor, helper_code + "\n__all__ = ", 1)
    print("Inserted helper before __all__")
else:
    c = c.rstrip() + helper_code + "\n"
    print("Appended helper to end of file")

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print("PATCHED - content_service.py has destination_image + all_destination_images")
