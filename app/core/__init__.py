from .config import configure_app
from .database import db, migrate, init_extensions
from .security import login_manager, register_context_processors
