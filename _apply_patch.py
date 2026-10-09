import pathlib, sys
p = pathlib.Path("scripts/seed_from_csv.py")
s = p.read_text(encoding="utf-8")
orig = s

# ---- Patch 1: seed_packages — commit every 50, log every 25 ----
old_loop = """        if i % 5 == 0:
            session.flush()
            log.info("  ...%d/%d packages", i, len(rows))

    session.flush()
    return created
"""
new_loop = """        # WHY: commit every 50 packages. Neon terminates connections that sit
        # idle in a transaction for > 5 minutes (idle_in_transaction_session_timeout).
        # A single uncommitted transaction across 1,645 packages takes ~24 min,
        # so it WILL eventually cross that 5-min idle window and be killed.
        # Committing in chunks bounds each transaction to well under a minute.
        # The seed is idempotent (matches by business key), so partial commits
        # are safe to re-run.
        if i % 25 == 0:
            log.info("  ...%d/%d packages", i, len(rows))
        if i % 50 == 0:
            session.commit()

    session.commit()
    return created
"""
assert old_loop in s, "Patch 1 target not found"
s = s.replace(old_loop, new_loop, 1)

# ---- Patch 2: _run — raise idle_in_transaction_session_timeout for seed session ----
old_ctx = """    with app.app_context():
        session: Session = db.session
        try:
"""
new_ctx = """    with app.app_context():
        session: Session = db.session
        # WHY: Neon defaults idle_in_transaction_session_timeout to 5 min.
        # Even with chunked commits, a single slow package insert could exceed
        # that and kill the connection. Raise it to 30 min for the seed process
        # only; the app runtime keeps the safer 5-min default.
        from sqlalchemy import text as _sql_text
        session.execute(_sql_text("SET SESSION idle_in_transaction_session_timeout = '30min'"))
        try:
"""
assert old_ctx in s, "Patch 2 target not found"
s = s.replace(old_ctx, new_ctx, 1)

if s == orig:
    print("NO CHANGES APPLIED — investigate")
    sys.exit(1)

p.write_text(s, encoding="utf-8")
print("Patch applied. Lines changed:", s.count("\n") - orig.count("\n"), "delta")

