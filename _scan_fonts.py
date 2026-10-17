import re
from pathlib import Path
from collections import Counter, defaultdict

# ── 1. Scan every CSS file ──────────────────────────────────────
css_fonts = defaultdict(list)   # font_name -> [(file, line)]

css_files = list(Path("static/css").rglob("*.css"))
for css in css_files:
    text = css.read_text(encoding="utf-8", errors="ignore")
    for i, line in enumerate(text.splitlines(), 1):
        # match font-family: ... ;
        for m in re.finditer(r"font-family\s*:\s*([^;}{]+)", line, re.IGNORECASE):
            value = m.group(1).strip()
            # extract the primary font name (first token before comma, strip quotes)
            first = value.split(",")[0].strip().strip("'\"").strip()
            css_fonts[first].append((str(css), i))

print("=" * 72)
print("FONT FAMILIES DECLARED IN CSS FILES")
print("=" * 72)
if not css_fonts:
    print("  (none)")
else:
    for font in sorted(css_fonts, key=lambda f: -len(css_fonts[f])):
        locations = css_fonts[font]
        print(f"  {font:30} {len(locations)} declaration(s)")
        for f, ln in locations[:5]:
            print(f"      {f}:{ln}")
        if len(locations) > 5:
            print(f"      ... and {len(locations) - 5} more")

# ── 2. Scan every template for <link> to Google Fonts ───────────
tpl_fonts = defaultdict(list)
tpl_files = list(Path("templates").rglob("*.html"))
google_font_re = re.compile(r"fonts\.googleapis\.com/css2?\?([^\"']+)", re.IGNORECASE)

for tpl in tpl_files:
    text = tpl.read_text(encoding="utf-8", errors="ignore")
    for m in google_font_re.finditer(text):
        query = m.group(1)
        # extract family=
        families = re.findall(r"family=([^&:]+)", query)
        for fam in families:
            name = fam.replace("+", " ").strip()
            tpl_fonts[name].append(str(tpl))

# Also check base.html for preconnect-only font references
print()
print("=" * 72)
print("GOOGLE FONTS LOADED IN TEMPLATES")
print("=" * 72)
if not tpl_fonts:
    print("  (none)")
else:
    for font, files in sorted(tpl_fonts.items()):
        print(f"  {font:30} loaded in: {', '.join(files)}")

# ── 3. Scan every inline <style> block in templates ─────────────
inline_fonts = defaultdict(list)
for tpl in tpl_files:
    text = tpl.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r"font-family\s*:\s*([^;}{]+)", text, re.IGNORECASE):
        value = m.group(1).strip()
        first = value.split(",")[0].strip().strip("'\"").strip()
        inline_fonts[first].append(str(tpl))

print()
print("=" * 72)
print("FONT FAMILIES DECLARED INLINE (<style> in templates)")
print("=" * 72)
if not inline_fonts:
    print("  (none)")
else:
    for font, files in sorted(inline_fonts.items()):
        unique = sorted(set(files))
        print(f"  {font:30} in: {', '.join(unique)}")

# ── 4. Scan every template for inline style= with font-family ───
inline_attr_fonts = defaultdict(list)
for tpl in tpl_files:
    text = tpl.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r'style\s*=\s*"[^"]*font-family\s*:\s*([^;"]+)', text, re.IGNORECASE):
        value = m.group(1).strip()
        first = value.split(",")[0].strip().strip("'\"").strip()
        inline_attr_fonts[first].append(str(tpl))

print()
print("=" * 72)
print("FONT FAMILIES IN INLINE style=\"font-family:...\" ATTRIBUTES")
print("=" * 72)
if not inline_attr_fonts:
    print("  (none)")
else:
    for font, files in sorted(inline_attr_fonts.items()):
        unique = sorted(set(files))
        print(f"  {font:30} in: {', '.join(unique)}")

# ── 5. Summary ─────────────────────────────────────────────────
print()
print("=" * 72)
print("SUMMARY")
print("=" * 72)
all_fonts = set(css_fonts.keys()) | set(tpl_fonts.keys()) | \
            set(inline_fonts.keys()) | set(inline_attr_fonts.keys())

# filter out generic fallbacks
generic = {"sans-serif", "serif", "monospace", "cursive", "fantasy",
           "system-ui", "ui-sans-serif", "ui-serif", "ui-monospace",
           "-apple-system", "blinkmacsystemfont", "segoe ui", "roboto",
           "helvetica neue", "arial", "noto sans"}

print(f"Total distinct font-family names found: {len(all_fonts)}")
print()
print("Real (non-fallback) fonts actually used:")
real_fonts = sorted(f for f in all_fonts if f.lower() not in generic)
for f in real_fonts:
    sources = []
    if f in css_fonts: sources.append(f"CSS({len(css_fonts[f])})")
    if f in tpl_fonts: sources.append("GoogleFonts")
    if f in inline_fonts: sources.append("inline-style")
    if f in inline_attr_fonts: sources.append("inline-attr")
    print(f"  {f:30} via {', '.join(sources)}")
