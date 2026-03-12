from app.core.extensions import db
from app.models import SystemLog


def log_action(action: str, object_type: str = None, object_id: str = None, user_id: int = None, details: str = None):
    try:
        entry = SystemLog(
            user_id=user_id,
            action=action,
            object_type=object_type,
            object_id=str(object_id) if object_id is not None else None,
            details=details,
        )
        db.session.add(entry)
        db.session.commit()
        return entry
    except Exception:
        db.session.rollback()
        return None
