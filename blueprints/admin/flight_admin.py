# -*- coding: utf-8 -*-
"""
blueprints/admin/flight_admin.py
Admin tab for flight CSV upload/download and browsing.
"""
from __future__ import annotations

from flask import (flash, redirect, render_template, request, url_for, Response, jsonify, current_app)
from sqlalchemy import select, func

from blueprints.admin import admin_bp, admin_required
from extensions import db
from models import FlightPrice
from services.flight_csv_service import import_csv, export_csv


@admin_bp.route("/flights")
@admin_required
def flight_admin_index():
    """List flight prices with filters."""
    page = max(1, int(request.args.get("page", 1) or 1))
    per_page = 50

    q_airline = (request.args.get("airline") or "").strip()
    q_origin = (request.args.get("origin") or "").strip().upper()
    q_dest = (request.args.get("destination") or "").strip().upper()
    q_dir = (request.args.get("direction") or "").strip().lower()

    stmt = select(FlightPrice)
    if q_airline:
        stmt = stmt.where(FlightPrice.airline.ilike(f"%{q_airline}%"))
    if q_origin:
        stmt = stmt.where(FlightPrice.origin == q_origin)
    if q_dest:
        stmt = stmt.where(FlightPrice.destination == q_dest)
    if q_dir in ("out", "back"):
        stmt = stmt.where(FlightPrice.direction == q_dir)

    stmt = stmt.order_by(
        FlightPrice.departure_date.desc(),
        FlightPrice.airline, FlightPrice.origin,
    )

    total = int(db.session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)

    rows = list(db.session.scalars(
        stmt.limit(per_page).offset((page - 1) * per_page)
    ))

    # Distinct list for filter dropdowns
    airlines = list(db.session.scalars(
        select(FlightPrice.airline).distinct().order_by(FlightPrice.airline)
    ))
    origins = list(db.session.scalars(
        select(FlightPrice.origin).distinct().order_by(FlightPrice.origin)
    ))
    destinations = list(db.session.scalars(
        select(FlightPrice.destination).distinct().order_by(FlightPrice.destination)
    ))

    return render_template(
        "admin/flight_admin.html",
        rows=rows,
        total=total,
        page=page,
        total_pages=total_pages,
        airlines=airlines,
        origins=origins,
        destinations=destinations,
        q_airline=q_airline,
        q_origin=q_origin,
        q_dest=q_dest,
        q_dir=q_dir,
    )


@admin_bp.route("/flights/import", methods=["GET", "POST"])
@admin_required
def flight_admin_import():
    """Upload a flight CSV."""
    if request.method == "POST":
        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            flash("Pick a CSV file first.", "warning")
            return redirect(url_for("admin.flight_admin_import"))

        replace = bool(request.form.get("replace"))
        inserted, updated, errors = import_csv(uploaded, replace=replace)

        flash(f"Imported: {inserted} inserted, {updated} updated.", "success")
        if errors:
            for e in errors[:10]:
                flash(e, "warning")
            if len(errors) > 10:
                flash(f"... and {len(errors) - 10} more errors.", "warning")

        return redirect(url_for("admin.flight_admin_index"))

    return render_template("admin/flight_import.html")


@admin_bp.route("/flights/export")
@admin_required
def flight_admin_export():
    """Stream all flight_prices as a CSV download."""
    body = export_csv()
    return Response(
        body,
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=flight_prices.csv",
        },
    )


@admin_bp.route("/flights/<int:fp_id>/delete", methods=["POST"])
@admin_required
def flight_admin_delete(fp_id: int):
    """Delete one flight_prices row."""
    fp = db.session.get(FlightPrice, fp_id)
    if fp is None:
        flash("Not found.", "warning")
        return redirect(url_for("admin.flight_admin_index"))
    db.session.delete(fp)
    db.session.commit()
    flash("Flight price removed.", "success")
    return redirect(url_for("admin.flight_admin_index"))

@admin_bp.route("/flights/delete-all", methods=["POST"])
@admin_required
def flight_admin_delete_all():
    """Delete every row in flight_prices. Requires an explicit confirm field."""
    confirmed = request.form.get("confirm_delete_all") == "yes"
    if not confirmed:
        flash("Tick the confirmation box first.", "warning")
        return redirect(url_for("admin.flight_admin_index"))

    try:
        n = db.session.query(FlightPrice).delete()
        db.session.commit()
        flash(f"Deleted {n} flight prices. You can now import a fresh CSV.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Delete failed: {e}", "danger")

    return redirect(url_for("admin.flight_admin_index"))

# ═══════════════════════════════════════════════════════════════════
# AUTO-MATCH FLIGHTS TO PACKAGES
# ═══════════════════════════════════════════════════════════════════

@admin_bp.route("/flights/auto-match/preview")
@admin_required
def flight_auto_match_preview():
    """Preview what auto-match would do (no DB changes)."""
    from services.flight_matching_service import preview_matches
    try:
        preview = preview_matches()
        return jsonify({
            "ok": True,
            "total_links": preview["total_links"],
            "destinations": preview["destinations"],
        })
    except Exception as e:
        current_app.logger.exception("Preview failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@admin_bp.route("/flights/auto-match/apply", methods=["POST"])
@admin_required
def flight_auto_match_apply():
    """Actually create the PackageFlight links."""
    from services.flight_matching_service import apply_matches
    try:
        result = apply_matches()
        return jsonify({
            "ok": True,
            "created": result["created"],
            "errors": result["errors"],
        })
    except Exception as e:
        current_app.logger.exception("Apply failed")
        db.session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
