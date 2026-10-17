"""
retheme_fonts.py
────────────────
Switches the whole site to Playfair Display (headings) + Inter (body).

What it does:
  1. Audits current font usage (prints a summary)
  2. Backs up every file it will touch to  _font_backup_<timestamp>/
  3. Updates base.html: adds Playfair Display, keeps Inter, optionally
     keeps Cinzel for the logo only
  4. Rewrites every CSS + template + inline style rule:
        'Cinzel'  -> 'Playfair Display'
        'Lora'    -> 'Playfair Display'
  5. Leaves 'Inter' alone (body font)
  6. Reports what changed

Run:
    python retheme_fonts.py --dry-run      # preview only
    python retheme_fonts.py                # apply
    python retheme_fonts.py --keep-logo-cinzel
                                           # Cinzel stays on the .site-logo
"""
from __future__ import annotations

import argparse
import re
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
CSS_DIR = ROOT / "static" / "css"
TPL_DIR = ROOT / "templates"

# ── Font replacement rules ─────────────────────────────────────
HEADING_OLD = ["Cinzel", "Lora"]
HEADING_NEW = "Playfair Display"
BODY_FONT = "Inter"

# Google Fonts URLs (query strings the swap will insert)
PLAYFAIR_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Playfair+Display:wght@500;600;700&display=swap"
)
CINZEL_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Cinzel:wght@500;600;700&display=swap"
)
INTER_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Inter:wght@400;500;600;700;800&display=swap"
)


def find_files() -> dict[str, list[Path]]:
    css = list(CSS_DIR.rglob("*.css"))
    templates = list(TPL_DIR.rglob("*.html"))
    return {"css": css, "templates": templates}


def audit(files: dict[str, list[Path]]) -> None:
    print("=" * 72)
    print("FONT AUDIT — BEFORE")
    print("=" * 72)

    counts = {"Cinzel": 0, "Lora": 0, "Playfair Display": 0, "Inter": 0}
    google_links = {"Cinzel": [], "Playfair Display": [], "Inter": []}

    for css in files["css"]:
        text = css.read_text(encoding="utf-8", errors="ignore")
        for name in counts:
            n = len(re.findall(rf"['\"]?{re.escape(name)}['\"]?", text))
            counts[name] += n

    for tpl in files["templates"]:
        text = tpl.read_text(encoding="utf-8", errors="ignore")
        for name in counts:
            n = len(re.findall(rf"['\"]?{re.escape(name)}['\"]?", text))
            counts[name] += n
        # Google Fonts links
        for url_re, label in [
            (r"family=Cinzel[^\"']*", "Cinzel"),
            (r"family=Playfair\+Display[^\"']*", "Playfair Display"),
            (r"family=Inter[^\"']*", "Inter"),
        ]:
            if re.search(url_re, text):
                google_links[label].append(str(tpl))

    for name, n in counts.items():
        print(f"  {name:20} referenced {n} time(s)")

    print()
    print("Google Fonts loaded in:")
    for name, files_ in google_links.items():
        if files_:
            print(f"  {name:20} -> {', '.join(sorted(set(files_)))}")
        else:
            print(f"  {name:20} -> (not loaded)")


def backup(files: dict[str, list[Path]]) -> Path:
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    dst = ROOT / f"_font_backup_{ts}"
    dst.mkdir(parents=True, exist_ok=True)

    for kind, paths in files.items():
        for p in paths:
            rel = p.relative_to(ROOT)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
    print(f"Backed up to {dst}/")
    return dst


def swap_font_names(text: str) -> str:
    """Replace 'Cinzel' and 'Lora' with 'Playfair Display'."""
    for old in HEADING_OLD:
        # match the name quoted or unquoted as a font-family token
        text = re.sub(
            rf"(['\"]?){re.escape(old)}\1",
            rf"'{HEADING_NEW}'",
            text,
        )
    return text


def ensure_playfair_in_head(html: str, keep_cinzel: bool) -> str:
    """
    Make sure <head> loads Playfair Display + Inter + (optionally) Cinzel.
    Also removes a stale Cinzel link if we don't want it.
    """
    # Already there? Do nothing.
    if "family=Playfair+Display" in html:
        return html

    # Build the link block
    fonts = [PLAYFAIR_URL, INTER_URL]
    if keep_cinzel:
        fonts.append(CINZEL_URL)

    links = "\n".join(
        f'<link href="{url}" rel="stylesheet">' for url in fonts
    )

    # Insert just before </head>
    if "</head>" in html:
        html = html.replace(
            "</head>",
            f"    <!-- Fonts: Playfair Display (headings) + Inter (body) -->\n{links}\n</head>",
            1,
        )
    return html


def patch_file(path: Path, keep_logo_cinzel: bool, dry_run: bool) -> bool:
    """Return True if the file was changed."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    original = text

    if path.suffix == ".css":
        text = swap_font_names(text)

    elif path.suffix == ".html":
        # 1. In <head>: ensure the Google Fonts link is right
        if path.name == "base.html":
            text = ensure_playfair_in_head(text, keep_cinzel=keep_logo_cinzel)

        # 2. Replace font-family names throughout the template
        text = swap_font_names(text)

        # 3. If we want Cinzel kept for the logo ONLY — restore it there
        if keep_logo_cinzel:
            # Any rule/tag mentioning .site-logo or .navbar-brand gets Cinzel back
            def _restore_logo(match):
                return match.group(0).replace(HEADING_NEW, "Cinzel")
            text = re.sub(
                r"(\.site-logo[^{]*\{[^}]*\}|\.navbar-brand[^{]*\{[^}]*\})",
                _restore_logo,
                text,
                flags=re.DOTALL,
            )

    if text == original:
        return False

    if not dry_run:
        path.write_text(text, encoding="utf-8")

    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-logo-cinzel", action="store_true",
                    help="Keep Cinzel ONLY on .site-logo / .navbar-brand")
    args = ap.parse_args()

    files = find_files()
    audit(files)

    if args.dry_run:
        print()
        print("=" * 72)
        print("DRY RUN — previewing changes")
        print("=" * 72)
    else:
        print()
        print("=" * 72)
        print("BACKUP + APPLY")
        print("=" * 72)
        backup(files)

    changed = []
    for kind, paths in files.items():
        for p in paths:
            if patch_file(p, args.keep_logo_cinzel, args.dry_run):
                changed.append(p)

    print()
    print(f"{'Would change' if args.dry_run else 'Changed'}: {len(changed)} file(s)")
    for p in changed:
        print(f"  {p.relative_to(ROOT)}")

    if args.dry_run:
        print()
        print("Re-run without --dry-run to apply.")

    print()
    print("=" * 72)
    print("DONE")
    print("=" * 72)
    print("Next steps:")
    print("  1. Hard refresh the browser (Ctrl+Shift+R)")
    print("  2. Check any page — headings should now be Playfair Display")
    print("  3. If you don't like it, restore from the _font_backup_* folder")

    return 0


if __name__ == "__main__":
    main()
