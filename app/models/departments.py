"""v64 domain export layer for departments.

These imports reduce dependency on wildcard compatibility wrappers while
keeping the project compatible with the existing PostgreSQL/SQLite schema.
Concrete model definitions still live in app.models_legacy for this version.
"""
from app.models_legacy import (
    Department,
    DepartmentLeader,
    DepartmentSubject,
    TeacherAttestation,
    TeacherCourse,
    TeacherLoad,
    TeacherMckoResult,
    TeacherProfessionalRecordChange,
)

__all__ = [
    "Department",
    "DepartmentLeader",
    "DepartmentSubject",
    "TeacherAttestation",
    "TeacherCourse",
    "TeacherLoad",
    "TeacherMckoResult",
    "TeacherProfessionalRecordChange",
]
