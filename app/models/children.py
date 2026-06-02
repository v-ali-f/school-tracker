"""v64 domain export layer for children.

These imports reduce dependency on wildcard compatibility wrappers while
keeping the project compatible with the existing PostgreSQL/SQLite schema.
Concrete model definitions still live in app.models_legacy for this version.
"""
from app.models_legacy import Child, ChildComment, ChildEnrollment, ChildEvent, ChildMovement, ChildParent, ChildSocial, ChildTransferHistory, Parent, ChildParent

__all__ = ['Child', 'ChildComment', 'ChildEnrollment', 'ChildEvent', 'ChildMovement', 'ChildParent', 'ChildSocial', 'ChildTransferHistory', 'Parent', 'ChildParent']
