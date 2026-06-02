import os
import traceback
from flask import request, render_template, redirect, url_for, flash
from werkzeug.utils import secure_filename

from ...importer import import_bp
from .import_attendance import parse_attendance_file


@import_bp.route("/attendance/import", methods=["GET", "POST"])
def attendance_import():

    if request.method == "POST":

        file = request.files.get("file")

        if not file or file.filename == "":
            flash("Файл не выбран", "danger")
            return redirect(url_for("importer.attendance_import"))

        try:

            upload_dir = os.path.join("school-tracker-storage", "uploads")
            os.makedirs(upload_dir, exist_ok=True)

            filepath = os.path.join(upload_dir, secure_filename(file.filename))
            file.save(filepath)

            records = parse_attendance_file(filepath)

            print("Найдено записей:", len(records))

            if records:
                print("Пример записи:", records[0])

            flash(f"Импортировано записей: {len(records)}", "success")

        except Exception as e:

            print("\n===== ОШИБКА ИМПОРТА =====")
            traceback.print_exc()
            print("===== КОНЕЦ ОШИБКИ =====\n")

            flash(f"Ошибка импорта: {e}", "danger")

        return redirect(url_for("importer.attendance_import"))

    return render_template("attendance/import.html")