from sqlalchemy import bindparam
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
    flash,
)
from flask_login import current_user, login_required

from app.core.extensions import db, csrf
from app.models.drive import DriveItem
from app.models import User


office_bp = Blueprint("office", __name__, url_prefix="/office")

OFFICE_EXTENSIONS = {"docx", "xlsx", "pptx"}


def _ensure_drive_access_table():
    engine_name = db.engine.dialect.name
    if engine_name == "postgresql":
        db.session.execute(db.text("""
            CREATE TABLE IF NOT EXISTS drive_item_access (
                id SERIAL PRIMARY KEY,
                item_id INTEGER NOT NULL REFERENCES drive_item(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                access_type VARCHAR(20) NOT NULL,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))
    else:
        db.session.execute(db.text("""
            CREATE TABLE IF NOT EXISTS drive_item_access (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                access_type VARCHAR(20) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))

    db.session.execute(db.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_drive_item_access_unique
        ON drive_item_access(item_id, user_id)
    """))
    db.session.commit()


def _shared_item_ids(access_types=("view", "edit")):
    _ensure_drive_access_table()
    rows = db.session.execute(
        db.text("""
            SELECT item_id
            FROM drive_item_access
            WHERE user_id = :user_id
              AND access_type IN :access_types
        """).bindparams(bindparam("access_types", expanding=True)),
        {
            "user_id": current_user.id,
            "access_types": tuple(access_types),
        },
    ).scalars().all()
    return list(rows)


def _user_access_type(item_id, user_id):
    _ensure_drive_access_table()
    return db.session.execute(
        db.text("""
            SELECT access_type
            FROM drive_item_access
            WHERE item_id = :item_id AND user_id = :user_id
            LIMIT 1
        """),
        {"item_id": item_id, "user_id": user_id},
    ).scalar()


def _access_rows(item_id):
    _ensure_drive_access_table()
    return db.session.execute(
        db.text("""
            SELECT user_id, access_type
            FROM drive_item_access
            WHERE item_id = :item_id
            ORDER BY user_id
        """),
        {"item_id": item_id},
    ).mappings().all()


def _user_label(user):
    fio = getattr(user, "fio", None)
    if fio:
        return fio
    parts = [
        getattr(user, "last_name", "") or "",
        getattr(user, "first_name", "") or "",
        getattr(user, "middle_name", "") or "",
    ]
    name = " ".join(p.strip() for p in parts if p and p.strip())
    return name or getattr(user, "username", "") or f"ID {user.id}"


def _upload_root() -> Path:
    return Path(current_app.config["UPLOAD_FOLDER"]) / "drive"


def _jwt_secret() -> str:
    configured = current_app.config.get("ONLYOFFICE_JWT_SECRET")
    if configured:
        return configured

    secret_file = Path("/opt/onlyoffice/onlyoffice_jwt_secret.txt")
    if secret_file.exists():
        return secret_file.read_text(encoding="utf-8").strip()

    return current_app.config.get("SECRET_KEY", "dev-secret-key")


def _onlyoffice_url() -> str:
    return current_app.config.get("ONLYOFFICE_URL", "http://10.172.85.55:8082").rstrip("/")


def _external_base_url() -> str:
    return current_app.config.get("PORTAL_PUBLIC_URL", "http://10.172.85.55").rstrip("/")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _jwt_encode(payload: dict, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_part = _b64url(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    payload_part = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signing_input = f"{header_part}.{payload_part}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_part}.{payload_part}.{_b64url(signature)}"


def _file_key(item: DriveItem) -> str:
    raw = f"{item.id}:{item.updated_at.timestamp() if item.updated_at else 0}:{item.storage_path}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _access_key(item: DriveItem) -> str:
    secret = current_app.config.get("SECRET_KEY", "dev-secret-key")
    raw = f"{item.id}:{item.storage_path}:{item.owner_user_id}"
    return hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def _check_access_key(item: DriveItem):
    key = request.args.get("key") or ""
    if not hmac.compare_digest(key, _access_key(item)):
        abort(403)


def _can_view_item(item: DriveItem) -> bool:
    if item.deleted_at is not None:
        return False
    if item.scope == "public":
        return True
    if item.owner_user_id == current_user.id:
        return True
    return _user_access_type(item.id, current_user.id) in {"view", "edit"}


def _can_edit_item(item: DriveItem) -> bool:
    if item.deleted_at is not None:
        return False
    if item.owner_user_id == current_user.id:
        return True
    if item.scope == "public":
        return True
    return _user_access_type(item.id, current_user.id) == "edit"


def _file_path(item: DriveItem) -> Path:
    return Path(current_app.config["UPLOAD_FOLDER"]) / item.storage_path


def _mime_for_ext(ext: str) -> str:
    return {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }.get(ext, mimetypes.guess_type(f"file.{ext}")[0] or "application/octet-stream")


def _doc_type(ext: str) -> str:
    if ext == "xlsx":
        return "cell"
    if ext == "pptx":
        return "slide"
    return "word"


def _editor_type(ext: str) -> str:
    if ext == "xlsx":
        return "spreadsheet"
    if ext == "pptx":
        return "presentation"
    return "document"


def _write_minimal_docx(path: Path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>''')
        z.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>''')
        z.writestr("word/document.xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body><w:p><w:r><w:t></w:t></w:r></w:p><w:sectPr/></w:body>
</w:document>''')


def _write_minimal_xlsx(path: Path):
    try:
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Лист1"
        wb.save(path)
        return
    except Exception:
        pass

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>''')
        z.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>''')
        z.writestr("xl/workbook.xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Лист1" sheetId="1" r:id="rId1"/></sheets></workbook>''')
        z.writestr("xl/_rels/workbook.xml.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>''')
        z.writestr("xl/worksheets/sheet1.xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>''')


def _write_minimal_pptx(path: Path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
</Types>''')
        z.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>''')
        z.writestr("ppt/presentation.xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>''')
        z.writestr("ppt/_rels/presentation.xml.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>''')
        z.writestr("ppt/slides/slide1.xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree/></p:cSld></p:sld>''')


def _create_blank_file(path: Path, ext: str):
    if ext == "docx":
        _write_minimal_docx(path)
    elif ext == "xlsx":
        _write_minimal_xlsx(path)
    elif ext == "pptx":
        _write_minimal_pptx(path)
    else:
        raise ValueError("Unsupported extension")


@office_bp.route("/", methods=["GET"])
@login_required
def index():
    items = (
        DriveItem.query
        .filter(
            DriveItem.kind == "file",
            DriveItem.deleted_at.is_(None),
            DriveItem.ext.in_(list(OFFICE_EXTENSIONS)),
        )
        .filter(
            db.or_(
                DriveItem.scope == "public",
                DriveItem.owner_user_id == current_user.id,
                DriveItem.id.in_(_shared_item_ids(("view", "edit"))),
            )
        )
        .order_by(DriveItem.updated_at.desc())
        .limit(50)
        .all()
    )
    return render_template("office_index.html", items=items)


@office_bp.route("/new/<ext>", methods=["GET", "POST"])
@login_required
def new_file(ext):
    ext = (ext or "").lower().strip(".")
    if ext not in OFFICE_EXTENSIONS:
        abort(404)

    default_names = {
        "docx": "Новый документ",
        "xlsx": "Новая таблица",
        "pptx": "Новая презентация",
    }

    if request.method == "POST":
        title = (request.form.get("title") or default_names[ext]).strip()
        scope = (request.form.get("scope") or "private").strip()
        if scope not in {"private", "public"}:
            scope = "private"

        if not title.lower().endswith(f".{ext}"):
            filename = f"{title}.{ext}"
        else:
            filename = title

        if scope == "private":
            target_dir = _upload_root() / "private" / str(current_user.id)
        else:
            target_dir = _upload_root() / "public"

        target_dir.mkdir(parents=True, exist_ok=True)

        unique = uuid.uuid4().hex
        stored_name = f"{unique}.{ext}"
        full_path = target_dir / stored_name

        _create_blank_file(full_path, ext)

        rel_path = str(full_path.relative_to(Path(current_app.config["UPLOAD_FOLDER"])))
        size = full_path.stat().st_size

        item = DriveItem(
            owner_user_id=current_user.id,
            parent_id=None,
            kind="file",
            scope=scope,
            name=filename,
            mime=_mime_for_ext(ext),
            size_bytes=size,
            storage_path=rel_path,
            ext=ext,
        )
        db.session.add(item)
        db.session.commit()

        flash("Файл создан в Диске и открыт в онлайн-офисе.", "success")
        return redirect(url_for("office.editor", item_id=item.id))

    return render_template("office_new.html", ext=ext, default_name=default_names[ext])


@office_bp.route("/editor/<int:item_id>", methods=["GET"])
@login_required
def editor(item_id):
    item = DriveItem.query.get_or_404(item_id)
    if item.kind != "file" or item.ext not in OFFICE_EXTENSIONS:
        abort(404)
    if not _can_view_item(item):
        abort(403)

    mode = "edit" if _can_edit_item(item) else "view"
    key = _access_key(item)
    base = _external_base_url()

    config = {
        "document": {
            "fileType": item.ext,
            "key": _file_key(item),
            "title": item.name,
            "url": f"{base}{url_for('office.download', item_id=item.id)}?key={key}",
            "permissions": {
                "edit": mode == "edit",
                "download": True,
                "print": True,
            },
        },
        "documentType": _doc_type(item.ext),
        "editorConfig": {
            "mode": mode,
            "lang": "ru",
            "callbackUrl": f"{base}{url_for('office.callback', item_id=item.id)}?key={key}",
            "user": {
                "id": str(current_user.id),
                "name": getattr(current_user, "fio", None) or getattr(current_user, "username", "Пользователь"),
            },
            "customization": {
                "autosave": True,
                "forcesave": True,
            },
        },
        "type": "desktop",
    }

    token = _jwt_encode(config, _jwt_secret())
    config["token"] = token

    return render_template(
        "office_editor.html",
        item=item,
        config=config,
        onlyoffice_url=_onlyoffice_url(),
    )





@office_bp.route("/rename/<int:item_id>", methods=["POST"])
@login_required
def rename_file(item_id):
    item = DriveItem.query.get_or_404(item_id)

    if item.kind != "file" or item.ext not in OFFICE_EXTENSIONS:
        abort(404)

    if not _can_edit_item(item):
        abort(403)

    new_name = (request.form.get("name") or "").strip()
    if not new_name:
        flash("Название файла не может быть пустым.", "danger")
        return redirect(request.referrer or url_for("office.index"))

    ext = item.ext.lower()
    if not new_name.lower().endswith("." + ext):
        new_name = f"{new_name}.{ext}"

    item.name = new_name
    item.updated_at = datetime.utcnow()
    db.session.commit()

    flash("Файл переименован.", "success")
    return redirect(request.referrer or url_for("office.index"))


@office_bp.route("/access/<int:item_id>", methods=["GET", "POST"])
@login_required
def access_file(item_id):
    item = DriveItem.query.get_or_404(item_id)

    if item.kind != "file" or item.ext not in OFFICE_EXTENSIONS:
        abort(404)

    if item.owner_user_id != current_user.id:
        abort(403)

    _ensure_drive_access_table()

    if request.method == "POST":
        db.session.execute(
            db.text("DELETE FROM drive_item_access WHERE item_id = :item_id"),
            {"item_id": item.id},
        )

        view_ids = request.form.getlist("view_user_ids")
        edit_ids = request.form.getlist("edit_user_ids")

        # Если пользователь выбран и там, и там — редактирование важнее просмотра.
        edit_set = {int(x) for x in edit_ids if x and int(x) != current_user.id}
        view_set = {int(x) for x in view_ids if x and int(x) != current_user.id and int(x) not in edit_set}

        for user_id in sorted(view_set):
            db.session.execute(
                db.text("""
                    INSERT INTO drive_item_access(item_id, user_id, access_type)
                    VALUES (:item_id, :user_id, 'view')
                """),
                {"item_id": item.id, "user_id": user_id},
            )

        for user_id in sorted(edit_set):
            db.session.execute(
                db.text("""
                    INSERT INTO drive_item_access(item_id, user_id, access_type)
                    VALUES (:item_id, :user_id, 'edit')
                """),
                {"item_id": item.id, "user_id": user_id},
            )

        db.session.commit()
        flash("Доступ к документу сохранён.", "success")
        return redirect(url_for("office.index"))

    rows = _access_rows(item.id)
    view_ids = [row["user_id"] for row in rows if row["access_type"] == "view"]
    edit_ids = [row["user_id"] for row in rows if row["access_type"] == "edit"]

    users = (
        User.query
        .filter(User.id != current_user.id)
        .filter(User.is_active_user.is_(True))
        .order_by(User.last_name.asc(), User.first_name.asc(), User.username.asc())
        .all()
    )

    return render_template(
        "office_access.html",
        item=item,
        users=users,
        view_ids=view_ids,
        edit_ids=edit_ids,
        user_label=_user_label,
    )


@office_bp.route("/delete/<int:item_id>", methods=["POST"])
@login_required
def delete_file(item_id):
    item = DriveItem.query.get_or_404(item_id)

    if item.kind != "file" or item.ext not in OFFICE_EXTENSIONS:
        abort(404)

    if not _can_edit_item(item):
        abort(403)

    item.deleted_at = datetime.utcnow()
    db.session.commit()

    flash("Файл удалён из онлайн-офиса и Диска.", "success")
    return redirect(url_for("office.index"))


@office_bp.route("/download/<int:item_id>", methods=["GET"])
def download(item_id):
    item = DriveItem.query.get_or_404(item_id)
    _check_access_key(item)

    if item.kind != "file" or item.ext not in OFFICE_EXTENSIONS:
        abort(404)

    full = _file_path(item)
    if not full.exists():
        abort(404)

    return send_file(full, as_attachment=False, download_name=item.name, mimetype=item.mime or _mime_for_ext(item.ext))


@csrf.exempt
@office_bp.route("/callback/<int:item_id>", methods=["POST"])
def callback(item_id):
    item = DriveItem.query.get_or_404(item_id)
    _check_access_key(item)

    payload = request.get_json(silent=True) or {}
    status = payload.get("status")

    current_app.logger.info(
        "ONLYOFFICE callback: item_id=%s status=%s has_url=%s",
        item_id,
        status,
        bool(payload.get("url")),
    )

    # 2 — документ готов к сохранению, 6 — force save.
    if status in (2, 6):
        file_url = payload.get("url")
        if file_url:
            try:
                # ONLYOFFICE отдаёт готовый файл по временной ссылке file_url.
                # Для этой ссылки отдельный AuthorizationJwt обычно не нужен.
                with urlopen(file_url, timeout=60) as response:
                    data = response.read()

                full = _file_path(item)
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_bytes(data)

                item.size_bytes = len(data)
                item.updated_at = datetime.utcnow()
                db.session.commit()
            except Exception:
                current_app.logger.exception("ONLYOFFICE callback save failed for DriveItem %s", item.id)
                return jsonify({"error": 1})

    return jsonify({"error": 0})
