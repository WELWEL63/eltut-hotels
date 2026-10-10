p = 'models/flight.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# Patch 1: add ForeignKey import if not present (it is, but be safe)
# Patch 2: add airline_id column right after supplier_id
old = '''    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )'''

new = '''    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Structured airline reference (preferred). Falls back to free-text
    # airline_name when NULL, so legacy flights still render.
    airline_id: Mapped[int | None] = mapped_column(
        ForeignKey("airlines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )'''

if old in c:
    c = c.replace(old, new, 1)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(c)
    print("✅ Flight.airline_id FK added")
else:
    print("❌ Anchor not found")
    idx = c.find("supplier_id")
    print("Context:", repr(c[idx-100:idx+400]))
    raise SystemExit(1)
