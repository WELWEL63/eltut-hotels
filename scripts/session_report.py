"""
scripts/session_report.py
─────────────────────────
Prints a complete snapshot of the project's current state so a fresh
session can resume without re-investigation.

Run:
    python -m scripts.session_report
    python -m scripts.session_report > _session_context.txt
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()
    except Exception as e:
        return f"(error: {e})"


def _section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def main() -> int:
    print(f"ELTUT TOURS — SESSION REPORT")
    print(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    print(f"CWD:       {Path.cwd()}")

    # 1. Git status + recent commits
    _section("1. GIT STATUS")
    print(_run(["git", "status", "-s"]) or "(clean working tree)")

    _section("2. RECENT COMMITS")
    print(_run(["git", "log", "--oneline", "-8"]))

    _section("3. BRANCH / REMOTE")
    print(_run(["git", "branch", "-vv"]))
    print()
    print(_run(["git", "remote", "-v"]))

    # 4. Env key presence (values hidden)
    _section("4. ENV KEYS (values hidden)")
    try:
        env = Path(".env")
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k = line.split("=", 1)[0].strip()
                    print(f"  {k}")
        else:
            print("  (.env not found)")
    except Exception as e:
        print(f"  (error: {e})")

    # 5. File inventory (top-level dirs)
    _section("5. FILE INVENTORY")
    for d in ["models", "services", "blueprints", "templates", "scripts",
              "migrations/versions", "mongo", "static/css", "cloud_function", "testing"]:
        p = Path(d)
        if p.is_dir():
            n = len(list(p.rglob("*")))
            print(f"  {d:30} {n} files")
        else:
            print(f"  {d:30} (missing)")

    # 6. Python syntax check
    _section("6. PYTHON SYNTAX CHECK")
    import ast
    bad = []
    for root in ["app.py", "config.py", "extensions.py", "utils.py",
                 "models", "services", "blueprints", "scripts", "mongo"]:
        p = Path(root)
        files = [p] if p.is_file() else list(p.rglob("*.py")) if p.is_dir() else []
        for f in files:
            try:
                ast.parse(f.read_text(encoding="utf-8-sig"), filename=str(f))
            except SyntaxError as e:
                bad.append(f"{f}:{e.lineno} {e.msg}")
    if bad:
        for b in bad:
            print(f"  FAIL {b}")
    else:
        print("  OK — every Python file parses")

    # 7. BOM check
    _section("7. BOM CHECK")
    bom = []
    for folder in ["app.py", "config.py", "models", "services", "blueprints",
                   "scripts", "mongo", "templates"]:
        p = Path(folder)
        files = [p] if p.is_file() else list(p.rglob("*")) if p.is_dir() else []
        for f in files:
            if f.is_file() and f.suffix in (".py", ".html", ".css"):
                try:
                    if f.read_bytes().startswith(b"\xef\xbb\xbf"):
                        bom.append(str(f))
                except Exception:
                    pass
    if bom:
        for b in bom[:20]:
            print(f"  BOM {b}")
        if len(bom) > 20:
            print(f"  ...and {len(bom) - 20} more")
    else:
        print("  OK — no BOM files")

    # 8. Template div balance
    _section("8. TEMPLATE DIV BALANCE")
    for tpl in ["templates/public/package_detail.html",
                "templates/public/booking_start.html",
                "templates/public/booking_confirmation.html",
                "templates/public/search_results.html",
                "templates/public/_filters_sidebar.html"]:
        p = Path(tpl)
        if p.exists():
            s = p.read_text(encoding="utf-8", errors="ignore")
            bal = s.count("<div") - s.count("</div>")
            status = "OK " if bal == 0 else "WARN"
            print(f"  {status} {tpl:60} <div={s.count('<div')} </div>={s.count('</div>')} balance={bal}")
        else:
            print(f"  MISSING {tpl}")

    # 9. Live app check
    _section("9. LIVE APP CHECK")
    try:
        from app import create_app
        app = create_app()
        client = app.test_client()
        for path in ["/", "/hotels", "/packages", "/activities",
                     "/search/results?type=package",
                     "/search/results?type=hotel",
                     "/search/results?type=activity"]:
            r = client.get(path)
            print(f"  {r.status_code}  {path}")
    except Exception as e:
        print(f"  (error: {e})")

    # 10. Health check
    _section("10. HEALTH CHECK")
    try:
        rc = subprocess.call([sys.executable, "-m", "scripts.health_check", "--quiet"])
        print(f"  exit code: {rc}")
    except Exception as e:
        print(f"  (error: {e})")

    # 11. DB counts
    _section("11. DATABASE COUNTS")
    try:
        from app import create_app
        from extensions import db
        from models import (Package, Hotel, Activity, Booking, Destination,
                            PackageFlight, PackagePrice, FlightPrice, Room, RoomRate)
        from sqlalchemy import select, func
        app = create_app()
        ctx = app.app_context()
        ctx.push()
        for name, model in [("destinations", Destination),
                            ("packages", Package),
                            ("package_flights", PackageFlight),
                            ("package_prices", PackagePrice),
                            ("hotels", Hotel),
                            ("rooms", Room),
                            ("room_rates", RoomRate),
                            ("activities", Activity),
                            ("flight_prices", FlightPrice),
                            ("bookings", Booking)]:
            n = db.session.scalar(select(func.count()).select_from(model))
            print(f"  {name:25} {n}")
        ctx.pop()
    except Exception as e:
        print(f"  (error: {e})")

    # 12. Instruction summary for next session
    _section("12. HOW TO RESUME")
    print("""
  Paste the output of this report into the new chat and say:

      "Resume eltut-tours-platform from the session report below."

  The assistant will know:
    - what's committed vs uncommitted
    - what pages exist and work
    - which template had layout fixes
    - the DB state (destinations, packages, bookings)
    - what remains (see PROJECT_STATE.md §6 'Known gaps')

  Key entry points:
    - templates/public/package_detail.html  (rewritten clean)
    - services/package_options_service.py   (single option source)
    - services/package_pricing_service.py   (compute_package_flight_card)
    - scripts/health_check.py               (run after every deploy)
    - PROJECT_STATE.md                      (business rules + session log)
    - README.md                             (setup + commands)
    """)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())