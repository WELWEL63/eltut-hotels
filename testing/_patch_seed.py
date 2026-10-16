import pathlib

p = pathlib.Path("scripts/seed_from_csv.py")
s = p.read_text(encoding="utf-8")
orig = s

# --- Patch 1: seed_packages - commit every 50, log every 25 ---
old_loop = (
    "        if i % 5 == 0:\n"
    "            session.flush()\n"
    '            log.info("  ...%d/%d packages", i, len(rows))\n'
    "\n"
    "    session.flush()\n"
    "    return created\n"
)

new_loop = (
    "        # WHY: commit every 50 packages. Neon terminates connections that\n"
    "        # sit idle in a transaction for more than 5 minutes. A single\n"
    "        # uncommitted transaction across 1645 packages takes ~24 min, so it\n"
    "        # will cross that 5-min idle window and be killed. Committing in\n"
    "        # chunks bounds each transaction to well under a minute. The seed\n"
    "        # is idempotent (matches by business key), so partial commits are\n"
    "        # safe to re-run.\n"
    "        if i % 25 == 0:\n"
    '            log.info("  ...%d/%d packages", i, len(rows))\n'
    "        if i % 50 == 0:\n"
    "            session.commit()\n"
    "\n"
    "    session.commit()\n"
    "    return created\n"
)

assert old_loop in s, "Patch 1 target not found"
s = s.replace(old_loop, new_loop, 1)

# --- Patch 2: _run - raise idle timeout for the seed session only ---
old_ctx = (
    "    with app.app_context():\n"
    "        session: Session = db.session\n"
    "        try:\n"
)

new_ctx = (
    "    with app.app_context():\n"
    "        session: Session = db.session\n"
    "        # WHY: Neon defaults idle_in_transaction_session_timeout to 5 min.\n"
    "        # Even with chunked commits, a single slow package insert could\n"
    "        # exceed that and kill the connection. Raise it to 30 min for the\n"
    "        # seed process only; app runtime keeps the safer 5-min default.\n"
    "        from sqlalchemy import text as _sql_text\n"
    "        session.execute(_sql_text(\n"
    '            "SET SESSION idle_in_transaction_session_timeout = \'30min\'"\n'
    "        ))\n"
    "        try:\n"
)

assert old_ctx in s, "Patch 2 target not found"
s = s.replace(old_ctx, new_ctx, 1)

if s == orig:
    print("NO CHANGES APPLIED")
    raise SystemExit(1)

p.write_text(s, encoding="utf-8")
print("Patch applied OK")
