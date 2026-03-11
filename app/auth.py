from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from .models import User

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        user = User.query.filter_by(username=username).first()

        if not user:
            print("LOGIN: user not found:", username)
            flash("Неверный логин или пароль", "danger")
            return render_template("login.html")

        if not user.check_password(password):
            print("LOGIN: password mismatch for:", username)
            flash("Неверный логин или пароль", "danger")
            return render_template("login.html")

        login_user(user)
        next_page = request.args.get("next")
        return redirect(url_for("main.dashboard"))

    return render_template("login.html")

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
