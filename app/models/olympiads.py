"""v64 domain export layer for olympiads.

These imports reduce dependency on wildcard compatibility wrappers while
keeping the project compatible with the existing PostgreSQL/SQLite schema.
Concrete model definitions still live in app.models_legacy for this version.
"""
from app.models_legacy import OlympiadImportSession, OlympiadResult, OlympiadStageMapping, OlympiadSubjectMapping, OlympiadUnmatchedRow

__all__ = ['OlympiadImportSession', 'OlympiadResult', 'OlympiadStageMapping', 'OlympiadSubjectMapping', 'OlympiadUnmatchedRow']
