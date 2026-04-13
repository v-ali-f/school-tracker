from datetime import datetime
from types import SimpleNamespace

from app.core.extensions import db


ACCESS_LEVEL_HIDDEN = "hidden"
ACCESS_LEVEL_VIEW = "view"
ACCESS_LEVEL_EDIT = "edit"
ACCESS_LEVEL_FULL = "full"

ACCESS_LEVELS = (
    ACCESS_LEVEL_HIDDEN,
    ACCESS_LEVEL_VIEW,
    ACCESS_LEVEL_EDIT,
    ACCESS_LEVEL_FULL,
)


class DashboardBlockCatalog(db.Model):
    __tablename__ = "dashboard_block_catalog"

    id = db.Column(db.Integer, primary_key=True)
    block_code = db.Column(db.String(100), nullable=False, unique=True, index=True)
    title = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(50), nullable=False, default="block", index=True)
    description = db.Column(db.Text, nullable=True)
    default_order = db.Column(db.Integer, nullable=False, default=100)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<DashboardBlockCatalog {self.block_code}>"


class RoleModuleAccess(db.Model):
    __tablename__ = "role_module_access"

    id = db.Column(db.Integer, primary_key=True)
    role_code = db.Column(db.String(64), nullable=False, index=True)
    module_code = db.Column(db.String(100), nullable=False, index=True)
    is_visible = db.Column(db.Boolean, nullable=False, default=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    access_level = db.Column(db.String(20), nullable=False, default=ACCESS_LEVEL_VIEW)
    display_order = db.Column(db.Integer, nullable=False, default=100)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("role_code", "module_code", name="uq_role_module_access_role_module"),
    )

    def __repr__(self):
        return f"<RoleModuleAccess {self.role_code}:{self.module_code}>"


class RoleDashboardBlock(db.Model):
    __tablename__ = "role_dashboard_block"

    id = db.Column(db.Integer, primary_key=True)
    role_code = db.Column(db.String(64), nullable=False, index=True)
    block_code = db.Column(db.String(100), nullable=False, index=True)
    is_visible = db.Column(db.Boolean, nullable=False, default=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    access_level = db.Column(db.String(20), nullable=False, default=ACCESS_LEVEL_VIEW)
    display_order = db.Column(db.Integer, nullable=False, default=100)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("role_code", "block_code", name="uq_role_dashboard_block_role_block"),
    )

    def __repr__(self):
        return f"<RoleDashboardBlock {self.role_code}:{self.block_code}>"


class RoleQuickLinkAccess(db.Model):
    __tablename__ = "role_quick_link_access"

    id = db.Column(db.Integer, primary_key=True)
    role_code = db.Column(db.String(64), nullable=False, index=True)
    quick_link_code = db.Column(db.String(100), nullable=False, index=True)
    is_visible = db.Column(db.Boolean, nullable=False, default=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    access_level = db.Column(db.String(20), nullable=False, default=ACCESS_LEVEL_VIEW)
    display_order = db.Column(db.Integer, nullable=False, default=100)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("role_code", "quick_link_code", name="uq_role_quick_link_role_link"),
    )

    def __repr__(self):
        return f"<RoleQuickLinkAccess {self.role_code}:{self.quick_link_code}>"


def empty_role_config():
    return SimpleNamespace(
        role_code=None,
        module_access=[],
        dashboard_blocks=[],
        quick_links=[],
    )


__all__ = [
    "ACCESS_LEVEL_HIDDEN",
    "ACCESS_LEVEL_VIEW",
    "ACCESS_LEVEL_EDIT",
    "ACCESS_LEVEL_FULL",
    "ACCESS_LEVELS",
    "DashboardBlockCatalog",
    "RoleModuleAccess",
    "RoleDashboardBlock",
    "RoleQuickLinkAccess",
    "empty_role_config",
]
