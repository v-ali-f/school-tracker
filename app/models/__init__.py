"""Canonical model import layer for v64.

The project now imports domain exports from app.models.* instead of relying on
blanket wildcard wrappers. Model classes still map to the existing database
schema in ``app.models_legacy`` to preserve compatibility with the current
PostgreSQL deployment.
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

from .diagnostics import *

from .service_staff import *

from .iom import *

from .organization import *

from .role_access import *

from .tasks import *

from .school_plan import *

from .kubok import *

from .page_visit import *

from .saved_view import *

from .max_binding import *

from .password_reset import *

from app.models_legacy import KnowledgeArticle, IncidentNote, IncidentNoteAttachment
