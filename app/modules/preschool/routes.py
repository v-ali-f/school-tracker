from flask import Blueprint, render_template

bp = Blueprint(
    "preschool",
    __name__,
    url_prefix="/preschool",
    template_folder="templates",
)


@bp.route("/")
def index():
    return render_template("preschool/index.html")


@bp.route("/children")
def children():
    return render_template("preschool/children.html")
