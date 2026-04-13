from app.models.role_access import (
    ACCESS_LEVEL_EDIT,
    ACCESS_LEVEL_FULL,
    ACCESS_LEVEL_HIDDEN,
    ACCESS_LEVEL_VIEW,
    DashboardBlockCatalog,
    RoleDashboardBlock,
    RoleModuleAccess,
    RoleQuickLinkAccess,
)


def _normalize_role(role_code):
    return (role_code or "").strip()


def get_role_module_access(role_code):
    role_code = _normalize_role(role_code)
    if not role_code:
        return []
    try:
        return (
            RoleModuleAccess.query
            .filter_by(role_code=role_code, is_active=True)
            .order_by(RoleModuleAccess.display_order.asc(), RoleModuleAccess.id.asc())
            .all()
        )
    except Exception:
        return []


def get_role_dashboard_blocks(role_code):
    role_code = _normalize_role(role_code)
    if not role_code:
        return []
    try:
        return (
            RoleDashboardBlock.query
            .filter_by(role_code=role_code, is_active=True)
            .order_by(RoleDashboardBlock.display_order.asc(), RoleDashboardBlock.id.asc())
            .all()
        )
    except Exception:
        return []


def get_role_quick_links(role_code):
    role_code = _normalize_role(role_code)
    if not role_code:
        return []
    try:
        return (
            RoleQuickLinkAccess.query
            .filter_by(role_code=role_code, is_active=True)
            .order_by(RoleQuickLinkAccess.display_order.asc(), RoleQuickLinkAccess.id.asc())
            .all()
        )
    except Exception:
        return []


def is_block_visible_for_role(role_code, block_code, *, fallback=True):
    role_code = _normalize_role(role_code)
    block_code = (block_code or "").strip()
    if not role_code or not block_code:
        return bool(fallback)
    try:
        item = (
            RoleDashboardBlock.query
            .filter_by(role_code=role_code, block_code=block_code, is_active=True)
            .first()
        )
    except Exception:
        item = None
    if not item:
        return bool(fallback)
    return bool(item.is_visible and item.is_enabled and item.access_level != ACCESS_LEVEL_HIDDEN)


def is_module_visible_for_role(role_code, module_code, *, fallback=True):
    role_code = _normalize_role(role_code)
    module_code = (module_code or "").strip()
    if not role_code or not module_code:
        return bool(fallback)
    try:
        item = (
            RoleModuleAccess.query
            .filter_by(role_code=role_code, module_code=module_code, is_active=True)
            .first()
        )
    except Exception:
        item = None
    if not item:
        return bool(fallback)
    return bool(item.is_visible and item.is_enabled and item.access_level != ACCESS_LEVEL_HIDDEN)


def get_role_access_level(role_code, object_code, object_type="block", *, fallback=ACCESS_LEVEL_VIEW):
    role_code = _normalize_role(role_code)
    object_code = (object_code or "").strip()
    if not role_code or not object_code:
        return fallback

    model = RoleDashboardBlock
    key = "block_code"
    if object_type == "module":
        model = RoleModuleAccess
        key = "module_code"
    elif object_type == "quick_link":
        model = RoleQuickLinkAccess
        key = "quick_link_code"

    try:
        item = model.query.filter_by(role_code=role_code, is_active=True, **{key: object_code}).first()
    except Exception:
        item = None
    if not item or not item.is_enabled:
        return fallback
    return item.access_level or fallback


def can_role_edit(role_code, object_code, object_type="block", *, fallback=False):
    level = get_role_access_level(role_code, object_code, object_type=object_type, fallback=None)
    if level is None:
        return bool(fallback)
    return level in {ACCESS_LEVEL_EDIT, ACCESS_LEVEL_FULL}


def get_dashboard_catalog(category=None):
    try:
        query = DashboardBlockCatalog.query.filter_by(is_active=True)
        if category:
            query = query.filter_by(category=category)
        return query.order_by(DashboardBlockCatalog.default_order.asc(), DashboardBlockCatalog.id.asc()).all()
    except Exception:
        return []


__all__ = [
    "get_role_module_access",
    "get_role_dashboard_blocks",
    "get_role_quick_links",
    "is_block_visible_for_role",
    "is_module_visible_for_role",
    "get_role_access_level",
    "can_role_edit",
    "get_dashboard_catalog",
]



def get_visible_dashboard_blocks_for_role(role_code, *, fallback_codes=None):
    items = get_role_dashboard_blocks(role_code)
    visible = [
        item for item in items
        if item.is_active and item.is_enabled and item.is_visible and item.access_level != ACCESS_LEVEL_HIDDEN
    ]
    if visible:
        return visible
    fallback_codes = fallback_codes or ["home_search", "home_summary", "home_quick_links", "home_sections"]
    result = []
    for idx, code in enumerate(fallback_codes, start=1):
        result.append(type("FallbackBlock", (), {
            "block_code": code,
            "display_order": idx * 10,
            "access_level": ACCESS_LEVEL_VIEW,
            "is_visible": True,
            "is_enabled": True,
        })())
    return result


def get_visible_quick_links_for_role(role_code, *, fallback_codes=None):
    items = get_role_quick_links(role_code)
    visible = [
        item for item in items
        if item.is_active and item.is_enabled and item.is_visible and item.access_level != ACCESS_LEVEL_HIDDEN
    ]
    if visible:
        return visible
    fallback_codes = fallback_codes or [
        "quick_search",
        "class_list",
        "attendance_pass_new",
        "incident_new",
        "control_works",
        "diagnostics",
        "olympiads",
        "service_staff",
        "iom",
    ]
    result = []
    for idx, code in enumerate(fallback_codes, start=1):
        result.append(type("FallbackQuick", (), {
            "quick_link_code": code,
            "display_order": idx * 10,
            "access_level": ACCESS_LEVEL_VIEW,
            "is_visible": True,
            "is_enabled": True,
        })())
    return result



def get_visible_modules_for_role(role_code, *, fallback_codes=None):
    items = get_role_module_access(role_code)
    visible = [
        item for item in items
        if item.is_active and item.is_enabled and item.is_visible and item.access_level != ACCESS_LEVEL_HIDDEN
    ]
    if visible:
        return visible
    fallback_codes = fallback_codes or [
        "dashboard",
        "children",
        "attendance",
        "incidents",
        "control_works",
        "diagnostics",
        "olympiads",
        "departments",
        "service_staff",
        "iom",
        "orders",
        "documents",
        "analytics",
        "admin",
    ]
    result = []
    for idx, code in enumerate(fallback_codes, start=1):
        result.append(type("FallbackModule", (), {
            "module_code": code,
            "display_order": idx * 10,
            "access_level": ACCESS_LEVEL_VIEW,
            "is_visible": True,
            "is_enabled": True,
        })())
    return result


def get_role_interface_context(role_code):
    modules = get_visible_modules_for_role(role_code)
    quick_links = get_visible_quick_links_for_role(role_code)
    blocks = get_visible_dashboard_blocks_for_role(role_code)

    module_codes = {getattr(item, "module_code", None) for item in modules if getattr(item, "module_code", None)}
    quick_codes = {getattr(item, "quick_link_code", None) for item in quick_links if getattr(item, "quick_link_code", None)}
    block_codes = {getattr(item, "block_code", None) for item in blocks if getattr(item, "block_code", None)}

    return {
        "role_modules": modules,
        "role_module_codes": module_codes,
        "role_quick_links": quick_links,
        "role_quick_link_codes": quick_codes,
        "role_dashboard_blocks": blocks,
        "role_block_codes": block_codes,
    }


def is_action_allowed_for_role(role_code, object_code, object_type="module", *, minimum="view", fallback=True):
    order = {
        ACCESS_LEVEL_HIDDEN: 0,
        ACCESS_LEVEL_VIEW: 1,
        ACCESS_LEVEL_EDIT: 2,
        ACCESS_LEVEL_FULL: 3,
    }
    current = get_role_access_level(role_code, object_code, object_type=object_type, fallback=None)
    if current is None:
        return bool(fallback)
    return order.get(current, 0) >= order.get(minimum, 1)
