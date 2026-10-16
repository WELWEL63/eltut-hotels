# -*- coding: utf-8 -*-
import io
path = "blueprints/admin/hotel_admin.py"
with io.open(path, encoding="utf-8") as f:
    c = f.read()

# Insert new route BEFORE room_rate_delete
anchor = '@admin_bp.route("/room-rates/<int:rate_id>/delete", methods=["POST"])'

new_route = '''@admin_bp.route("/room-rates/<int:rate_id>/edit", methods=["POST"])
@admin_required
def room_rate_edit(rate_id: int):
    """Edit an existing seasonal rate window."""
    rate = db.session.get(RoomRate, rate_id)
    if rate is None:
        abort(404)

    def _float(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    def _date(v):
        v = (v or "").strip()
        if not v:
            return None
        from datetime import datetime as _dt
        try:
            return _dt.strptime(v, "%Y-%m-%d").date()
        except ValueError:
            return None

    rate.adult_price = _float(request.form.get("adult_price"))
    rate.child_price = _float(request.form.get("child_price"))
    rate.currency = (request.form.get("currency") or "GBP").upper()
    rate.valid_from = _date(request.form.get("valid_from"))
    rate.valid_to = _date(request.form.get("valid_to"))

    db.session.commit()
    _log("update", "room_rate", rate.id,
         new=f"{rate.valid_from}->{rate.valid_to}")
    flash("Rate updated.", "success")
    return redirect(url_for("admin.room_edit", room_id=rate.room_id))


'''

if "def room_rate_edit" in c:
    print("Already added")
elif anchor in c:
    c = c.replace(anchor, new_route + anchor, 1)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("room_rate_edit route added")
else:
    print("Anchor not found")