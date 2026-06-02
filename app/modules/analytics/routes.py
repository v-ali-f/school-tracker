from flask import Blueprint, abort, render_template, request
from flask_login import login_required

from .permissions import can_view_analytics
from .services import build_analytics_payload

analytics_bp = Blueprint("analytics", __name__, url_prefix="/analytics")


@analytics_bp.route("/")
@login_required
def dashboard():
    if not can_view_analytics():
        abort(403)
    year_id = request.args.get("year_id", type=int)
    data = build_analytics_payload(year_id)
    return render_template("analytics_dashboard.html", **data, selected_year_id=(data["current_year"].id if data.get("current_year") else None))
