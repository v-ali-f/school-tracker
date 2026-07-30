from flask import current_app


WORKLOAD_MODULE = "workload_module"
WORKLOAD_WRITE = "workload_write"
WORKLOAD_NEW_SOURCE = "workload_new_source"

_CONFIG_KEYS = {
    WORKLOAD_MODULE: "FEATURE_WORKLOAD_MODULE_ENABLED",
    WORKLOAD_WRITE: "FEATURE_WORKLOAD_WRITE_ENABLED",
    WORKLOAD_NEW_SOURCE: "FEATURE_WORKLOAD_NEW_SOURCE_ENABLED",
}


def is_feature_enabled(feature_code: str) -> bool:
    """Return False for unknown or disabled features."""
    config_key = _CONFIG_KEYS.get((feature_code or "").strip())
    if not config_key:
        return False
    return bool(current_app.config.get(config_key, False))


def workload_feature_state() -> dict[str, bool]:
    return {
        "module": is_feature_enabled(WORKLOAD_MODULE),
        "write": is_feature_enabled(WORKLOAD_WRITE),
        "new_source": is_feature_enabled(WORKLOAD_NEW_SOURCE),
    }


__all__ = [
    "WORKLOAD_MODULE",
    "WORKLOAD_WRITE",
    "WORKLOAD_NEW_SOURCE",
    "is_feature_enabled",
    "workload_feature_state",
]
