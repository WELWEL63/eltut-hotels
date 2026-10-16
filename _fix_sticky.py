path = "templates/public/package_detail.html"
s = open(path, "r", encoding="utf-8-sig").read()

old = '''@media (min-width: 992px) {
    .pkg-layout {
        grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr) !important;
    }
    .pkg-aside > .card {
        position: sticky !important;
        top: 1rem !important;
    }
}'''

new = '''@media (min-width: 992px) {
    .pkg-layout {
        grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr) !important;
    }
    /* Sticky the ASIDE itself (grid item) — not the card inside,
       because a short parent blocks the child's sticky behaviour. */
    .pkg-aside {
        position: sticky !important;
        top: 1rem !important;
        align-self: start !important;
        max-height: calc(100vh - 2rem);
        overflow-y: auto;
    }
}'''

if old in s:
    s = s.replace(old, new, 1)
    open(path, "w", encoding="utf-8").write(s)
    print("sticky CSS updated")
else:
    print("old CSS block not found — checking current state")
    # Show what's there
    import re
    m = re.search(r'@media \(min-width:\s*992px\).{0,400}', s, re.DOTALL)
    if m:
        print(m.group(0))
