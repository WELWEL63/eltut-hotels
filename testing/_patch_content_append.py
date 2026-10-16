p = 'services/content_service.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

if "def destination_image(" in c:
    print("Already patched - no change")
    raise SystemExit(0)

helper = '''

# ─── Destination images (home page) ──────────────────────────────
def destination_image(slug, fallback=None):
    """Return the image URL for a destination slug, or None."""
    if not slug:
        return fallback or get("destination_image_default", None)
    value = get("destination_image_" + slug, None)
    if value:
        return value
    if fallback:
        return fallback
    return get("destination_image_default", None)


def all_destination_images():
    """Return {slug: image_url} for every destination_image_* key with a value."""
    values = all_values()
    prefix = "destination_image_"
    out = {}
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

with open(p, 'w', encoding='utf-8') as f:
    f.write(c.rstrip() + helper + "\n")

print("APPENDED")
