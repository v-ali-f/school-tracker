"""Canonical model import layer for v63.

This package is the primary import surface for application models.
During the v63 transition, concrete SQLAlchemy model classes still live in
app.models_legacy and are re-exported here by domain.
"""
from .academic import *
from .analytics import *
from .children import *
from .classes import *
from .control_works import *
from .departments import *
from .documents import *
from .olympiads import *
from .support import *
from .users import *

# Additional models not yet fully split by domain are re-exported here.
from app.models_legacy import *  # noqa: F401,F403
