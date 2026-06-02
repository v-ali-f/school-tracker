"""v64 domain export layer for support.

These imports reduce dependency on wildcard compatibility wrappers while
keeping the project compatible with the existing PostgreSQL/SQLite schema.
Concrete model definitions still live in app.models_legacy for this version.
"""
from app.models_legacy import Debt, Incident, IncidentChild, SupportCase, SystemLog

__all__ = ['Debt', 'Incident', 'IncidentChild', 'SupportCase', 'SystemLog']
