from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path):
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_large_workspace_templates_use_external_page_assets():
    expectations = {
        "app/templates/tasks/list.html": ("tasks_list.css",),
        "app/templates/incidents_my.html": ("incidents_my.css",),
        "app/templates/contingent.html": (
            "contingent_page.css",
            "contingent_page.js",
        ),
        "app/templates/workload/assignment_workspace.html": (
            "workload_assignment_workspace.js",
        ),
    }

    for template_path, asset_names in expectations.items():
        template = _read(template_path)
        for asset_name in asset_names:
            assert asset_name in template

    assert "<style" not in _read("app/templates/tasks/list.html")
    assert "<style" not in _read("app/templates/incidents_my.html")
    assert "<style" not in _read("app/templates/contingent.html")
    assert "<script>" not in _read("app/templates/contingent.html")
    assert "<script>" not in _read(
        "app/templates/workload/assignment_workspace.html"
    )


def test_confirmed_legacy_files_stay_removed():
    removed_paths = (
        "app/core.py",
        "app/orders_registry.py",
        "app/templates/movements_registry.html",
        "app/templates/support_registry_v44.html",
        "app/templates/system_logs.html",
    )

    for relative_path in removed_paths:
        assert not (PROJECT_ROOT / relative_path).exists()
