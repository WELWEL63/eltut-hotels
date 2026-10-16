# -*- coding: utf-8 -*-
"""
blueprints/admin/hotel_csv_admin.py
Admin tab: hotel CSV import/export.
"""
from __future__ import annotations

from flask import (
    flash, redirect, render_template, request, url_for, Response,
)
from sqlalchemy import select, func

from blueprints.admin import admin_bp, admin_required
from extensions import db
from models import Hotel, Room, RoomRate
from services.hotel_csv_service import import_csv, export_csv


@admin_bp.route("/hotel-csv")
@admin_required
def hotel_csv_index():
    """Summary page: counts + import/export buttons."""
    hotel_count = db.session.scalar(select(func.count(Hotel.id)))
    room_count = db.session.scalar(select(func.count(Room.id)))
    rate_count = db.session.scalar(select(func.count(RoomRate.id)))
    return render_template(
        "admin/hotel_csv.html",
        hotel_count=hotel_count,
        room_count=room_count,
        rate_count=rate_count,
    )


@admin_bp.route("/hotel-csv/import", methods=["GET", "POST"])
@admin_required
def hotel_csv_import():
    if request.method == "POST":
        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            flash("Pick a CSV file first.", "warning")
            return redirect(url_for("admin.hotel_csv_import"))

        replace = bool(request.form.get("replace"))
        new_hotels, new_rooms, new_rates, errors = import_csv(
            uploaded, replace=replace
        )
        flash(
            f"Imported: {new_hotels} hotels, {new_rooms} rooms, "
            f"{new_rates} rates.",
            "success",
        )
        for e in errors[:10]:
            flash(e, "warning")
        return redirect(url_for("admin.hotel_csv_index"))

    return render_template("admin/hotel_csv_import.html")


@admin_bp.route("/hotel-csv/export")
@admin_required
def hotel_csv_export():
    body = export_csv()
    return Response(
        body,
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=hotels_export.csv",
        },
    )