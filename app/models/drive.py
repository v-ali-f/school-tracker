"""Drive: личное и общее файловое хранилище + сборы файлов.

Сессия Drive (12.05.2026). MVP по запросу пользователей:
- «Мои файлы» — приватное хранилище per-user, квота 1 ГБ.
- «Общедоступные» — общая область, читать/писать могут все авторизованные.
- Сборы файлов — «зам говорит собираем сканы приказов»: создатель указывает
  адресатов (роли или конкретные user_id) + дедлайн + сколько файлов
  можно сдать; у адресата появляется задача «нужно сдать», после сдачи —
  файл попадает в папку сбора у создателя.
"""
from datetime import datetime

from app.core.extensions import db


# Простые иерархические папки + файлы в одной таблице (kind=folder|file).
class DriveItem(db.Model):
    __tablename__ = "drive_item"

    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("drive_item.id", ondelete="CASCADE"), nullable=True, index=True)

    # 'folder' | 'file'
    kind = db.Column(db.String(10), nullable=False)
    # 'private' (видит только owner) | 'public' (видят все авторизованные)
    scope = db.Column(db.String(10), nullable=False, default="private", index=True)

    name = db.Column(db.String(255), nullable=False)
    mime = db.Column(db.String(120), nullable=True)
    size_bytes = db.Column(db.BigInteger, nullable=False, default=0)
    storage_path = db.Column(db.String(500), nullable=True)  # относительно UPLOAD_FOLDER, только для file
    ext = db.Column(db.String(20), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True, index=True)

    owner = db.relationship("User", foreign_keys=[owner_user_id])
    parent = db.relationship("DriveItem", remote_side=[id], backref=db.backref("children", lazy="dynamic"))

    __table_args__ = (
        db.Index("ix_drive_item_owner_scope_parent", "owner_user_id", "scope", "parent_id"),
        db.Index("ix_drive_item_scope_parent", "scope", "parent_id"),
    )


class FileCollection(db.Model):
    __tablename__ = "file_collection"

    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)

    max_files_per_user = db.Column(db.Integer, nullable=False, default=1)  # 1+ файлов на пользователя
    deadline_at = db.Column(db.DateTime, nullable=False)
    allow_late = db.Column(db.Boolean, nullable=False, default=True, server_default="true")

    status = db.Column(db.String(20), nullable=False, default="open", index=True)  # open | closed

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)

    owner = db.relationship("User", foreign_keys=[owner_user_id])
    targets = db.relationship(
        "FileCollectionTarget",
        backref="collection",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    submissions = db.relationship(
        "FileCollectionSubmission",
        backref="collection",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )


# Один таргет — либо роль (role_code не пуст), либо конкретный user (user_id не пуст).
class FileCollectionTarget(db.Model):
    __tablename__ = "file_collection_target"

    id = db.Column(db.Integer, primary_key=True)
    collection_id = db.Column(db.Integer, db.ForeignKey("file_collection.id", ondelete="CASCADE"), nullable=False, index=True)
    role_code = db.Column(db.String(40), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)

    user = db.relationship("User", foreign_keys=[user_id])


class FileCollectionSubmission(db.Model):
    __tablename__ = "file_collection_submission"

    id = db.Column(db.Integer, primary_key=True)
    collection_id = db.Column(db.Integer, db.ForeignKey("file_collection.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)

    file_name = db.Column(db.String(255), nullable=False)
    storage_path = db.Column(db.String(500), nullable=False)
    mime = db.Column(db.String(120), nullable=True)
    size_bytes = db.Column(db.BigInteger, nullable=False, default=0)
    ext = db.Column(db.String(20), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        db.Index("ix_collection_submission_col_user", "collection_id", "user_id"),
    )
