from flask import current_app

def register_context_processors(app, has_permission, build_menu_flags):
    @app.context_processor
    def inject_permissions():
        def can(permission_code: str):
            return has_permission(permission_code)
        return {"can": can, **build_menu_flags()}

    @app.context_processor
    def inject_helpers():
        def endpoint_exists(endpoint_name: str) -> bool:
            return endpoint_name in current_app.view_functions
        return dict(endpoint_exists=endpoint_exists)
