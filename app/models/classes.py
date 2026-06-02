"""v64 domain export layer for classes.

These imports reduce dependency on wildcard compatibility wrappers while
keeping the project compatible with the existing PostgreSQL/SQLite schema.
Concrete model definitions still live in app.models_legacy for this version.
"""
from app.models_legacy import AcademicYear, Building, SchoolClass, Subject

__all__ = ['AcademicYear', 'Building', 'SchoolClass', 'Subject']
