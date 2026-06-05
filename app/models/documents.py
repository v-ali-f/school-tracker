"""v64 domain export layer for documents.

These imports reduce dependency on wildcard compatibility wrappers while
keeping the project compatible with the existing PostgreSQL/SQLite schema.
Concrete model definitions still live in app.models_legacy for this version.
"""
from app.models_legacy import (
    Document,
    DocumentRegistryAccess,
    DocumentRegistryRecord,
    OrderResponsible,
    OrderResponsibleLink,
    SchoolOrder,
)

__all__ = [
    'Document',
    'DocumentRegistryAccess',
    'DocumentRegistryRecord',
    'OrderResponsible',
    'OrderResponsibleLink',
    'SchoolOrder',
]
