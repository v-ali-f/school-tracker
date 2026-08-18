"""Build aSc Timetables XML from distributed workload assignments."""

from collections import defaultdict
from decimal import Decimal
from hashlib import sha1
from xml.etree import ElementTree

from app.services.teaching_group_display_service import (
    teaching_group_assignment_label,
    teaching_group_class_names,
    teaching_group_source_groups,
)


ZERO = Decimal("0")


def _clean(value, fallback=""):
    return " ".join(str(value or fallback).split())


def _short(value, fallback, limit=40):
    return (_clean(value) or _clean(fallback))[:limit]


def _teacher_short_name(teacher):
    initials = "".join(
        f"{part.strip()[0]}."
        for part in (teacher.first_name, teacher.middle_name)
        if part and part.strip()
    )
    return _short(
        f"{_clean(teacher.last_name)} {initials}".strip(),
        teacher.fio or teacher.username,
        40,
    )


def _decimal_text(value):
    text = format(Decimal(value or ZERO), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _class_key(name):
    return _clean(name).casefold().replace("ё", "е")


def _fallback_class_id(name):
    digest = sha1(_class_key(name).encode("utf-8")).hexdigest()[:12]
    return f"altair_class_name_{digest}"


def _source_group_plan(source_group):
    line = getattr(source_group, "source_plan_line", None)
    plan = getattr(line, "education_plan", None)
    root_plan = getattr(plan, "root_plan", None) or plan
    if root_plan is None:
        return None, ""
    return root_plan.id, _clean(
        getattr(root_plan, "profile_name", None)
        or getattr(root_plan, "name", None),
        f"УП {root_plan.id}",
    )


def _group_class_candidates(group):
    result = []
    seen = set()
    for source_group in teaching_group_source_groups(group):
        for link in getattr(source_group, "source_classes", None) or ():
            snapshot_class = link.population_snapshot_class
            if snapshot_class is None or not snapshot_class.name_snapshot:
                continue
            base_key = _class_key(snapshot_class.name_snapshot)
            plan_id, plan_label = _source_group_plan(source_group)
            grade = getattr(snapshot_class, "grade_snapshot", None)
            candidate_key = (
                (base_key, plan_id)
                if grade in {10, 11} and plan_id is not None
                else (base_key, None)
            )
            if candidate_key in seen:
                continue
            seen.add(candidate_key)
            source_id = getattr(snapshot_class, "source_school_class_id", None)
            result.append({
                "key": base_key,
                "base_key": base_key,
                "name": _clean(snapshot_class.name_snapshot),
                "base_name": _clean(snapshot_class.name_snapshot),
                "grade": grade,
                "plan_id": plan_id,
                "plan_label": plan_label,
                "source_id": source_id,
                "group_name": _clean(
                    teaching_group_assignment_label(source_group),
                    source_group.name,
                ),
                "entire_class": _is_entire_class(source_group),
                "source_plan_line_id": source_group.source_plan_line_id,
                "priority": 1,
                "id": (
                    f"altair_class_{source_id}"
                    if source_id is not None
                    else f"altair_snapshot_class_{snapshot_class.id}"
                ),
            })
    if result:
        return result

    for name in teaching_group_class_names(group):
        key = _class_key(name)
        fallback_key = (key, None)
        if key and fallback_key not in seen:
            seen.add(fallback_key)
            result.append({
                "key": key,
                "base_key": key,
                "name": _clean(name),
                "base_name": _clean(name),
                "grade": None,
                "plan_id": None,
                "plan_label": "",
                "source_id": None,
                "group_name": _clean(
                    teaching_group_assignment_label(group),
                    group.name,
                ),
                "entire_class": _is_entire_class(group),
                "source_plan_line_id": group.source_plan_line_id,
                "priority": 0,
                "id": _fallback_class_id(name),
            })
    if result:
        return result

    name = _clean(getattr(group, "name", None), f"Группа {group.id}")
    key = f"synthetic-group:{group.id}"
    return [{
        "key": key,
        "base_key": key,
        "name": name,
        "base_name": name,
        "grade": None,
        "plan_id": None,
        "plan_label": "",
        "source_id": None,
        "group_name": _clean(
            teaching_group_assignment_label(group),
            group.name,
        ),
        "entire_class": _is_entire_class(group),
        "source_plan_line_id": group.source_plan_line_id,
        "priority": 0,
        "id": f"altair_cohort_{group.id}",
    }]


def _is_entire_class(group):
    if group.group_type == "CLASS":
        return True
    if group.group_type not in {"EXTRACURRICULAR_GROUP", "ADDITIONAL_GROUP"}:
        return False
    links = getattr(group, "source_classes", None) or ()
    return len(links) == 1 and links[0].relation_kind == "FULL"


def build_asc_timetable_xml(assignments, classrooms=()):
    """Return UTF-8 aSc Timetables XML for active workload assignments.

    aSc discontinued GROUPSTYPE2. With supported GROUPSTYPE1, every imported
    group belongs to exactly one class and joined/metagroup lessons reference
    several per-class groups through ``groupids``.
    """
    active_assignments = [
        item for item in assignments
        if item.status != "CANCELLED"
        and Decimal(item.weekly_hours or ZERO) > ZERO
        and item.workload_need is not None
        and item.workload_need.teaching_group is not None
    ]
    active_classrooms = [
        item for item in classrooms if getattr(item, "is_active", True)
    ]

    teachers = {}
    subjects = {}
    groups = {}
    lesson_hours = defaultdict(lambda: ZERO)

    for assignment in active_assignments:
        need = assignment.workload_need
        group = need.teaching_group
        activity = need.education_activity
        group_id = f"altair_group_{group.id}"
        subject_id = f"altair_subject_{activity.id}"
        teacher_id = ""
        if assignment.employee is not None:
            teacher_id = f"altair_teacher_{assignment.employee.id}"
            teachers[teacher_id] = assignment.employee
        subjects[subject_id] = activity

        class_candidates = _group_class_candidates(group)
        groups[group_id] = {
            "group": group,
            "class_candidates": tuple(class_candidates),
        }
        lesson_hours[(group_id, subject_id, teacher_id)] += Decimal(
            assignment.weekly_hours
        )

    # aSc treats a class as one scheduling unit. For grades 10–11, pupils
    # assigned to different curricula must therefore be exported as separate
    # virtual classes. This also lets one metagroup join two curricula of the
    # same registry class without GROUPSTYPE2.
    plans_by_class = defaultdict(set)
    for item in groups.values():
        for candidate in item["class_candidates"]:
            if (
                candidate["grade"] in {10, 11}
                and candidate["plan_id"] is not None
            ):
                plans_by_class[candidate["base_key"]].add(
                    candidate["plan_id"]
                )

    classes_by_key = {}
    for item in groups.values():
        normalized_candidates = []
        for original in item["class_candidates"]:
            candidate = dict(original)
            split_by_plan = (
                candidate["grade"] in {10, 11}
                and candidate["plan_id"] is not None
                and len(plans_by_class[candidate["base_key"]]) > 1
            )
            if split_by_plan:
                candidate["key"] = (
                    f"{candidate['base_key']}::plan:{candidate['plan_id']}"
                )
                candidate["name"] = (
                    f"{candidate['base_name']} · {candidate['plan_label']}"
                )
                candidate["id"] = (
                    f"altair_class_{candidate['source_id']}"
                    f"_plan_{candidate['plan_id']}"
                    if candidate["source_id"] is not None
                    else _fallback_class_id(candidate["key"])
                )
            existing = classes_by_key.get(candidate["key"])
            if (
                existing is None
                or candidate["priority"] > existing["priority"]
            ):
                classes_by_key[candidate["key"]] = candidate
            normalized_candidates.append(candidate)
        item["class_candidates"] = tuple(normalized_candidates)

    root = ElementTree.Element(
        "timetable",
        {
            "importtype": "database",
            "options": "idprefix:Altair,groupstype1,decimalseparatordot",
            "displayname": "Altair workload export",
            "displaycountries": "",
        },
    )

    classroom_id_by_teacher_id = {}
    for classroom in active_classrooms:
        if classroom.teacher_user_id is not None:
            classroom_id_by_teacher_id[
                f"altair_teacher_{classroom.teacher_user_id}"
            ] = f"altair_classroom_{classroom.id}"

    teachers_node = ElementTree.SubElement(
        root,
        "teachers",
        {
            "options": "",
            # The aSc XML teacher table has no supported teacher-room column.
            # Concrete teacher rooms are therefore attached to every native
            # lesson below, where aSc does support ``classroomids``.
            "columns": "id,name,short",
        },
    )
    for teacher_id, teacher in sorted(
        teachers.items(), key=lambda item: item[1].fio.casefold()
    ):
        ElementTree.SubElement(teachers_node, "teacher", {
            "id": teacher_id,
            "name": _clean(teacher.fio, teacher.username),
            "short": _teacher_short_name(teacher),
        })

    subjects_node = ElementTree.SubElement(
        root,
        "subjects",
        {"options": "", "columns": "id,name,short"},
    )
    for subject_id, activity in sorted(
        subjects.items(), key=lambda item: item[1].name.casefold()
    ):
        ElementTree.SubElement(subjects_node, "subject", {
            "id": subject_id,
            "name": _clean(activity.name, activity.code),
            "short": _short(activity.short_name, activity.name, 40),
        })

    classrooms_node = ElementTree.SubElement(
        root,
        "classrooms",
        {"options": "", "columns": "id,name,short,capacity"},
    )
    for classroom in sorted(
        active_classrooms,
        key=lambda item: (item.name.casefold(), item.id),
    ):
        classroom_id = f"altair_classroom_{classroom.id}"
        ElementTree.SubElement(classrooms_node, "classroom", {
            "id": classroom_id,
            "name": _clean(classroom.name, classroom.short_name),
            "short": _short(classroom.short_name, classroom.name, 40),
            "capacity": (
                str(classroom.capacity)
                if classroom.capacity is not None else ""
            ),
        })

    classes_node = ElementTree.SubElement(
        root,
        "classes",
        {"options": "", "columns": "id,name,short"},
    )
    for class_item in sorted(
        classes_by_key.values(), key=lambda item: item["name"].casefold()
    ):
        ElementTree.SubElement(classes_node, "class", {
            "id": class_item["id"],
            "name": class_item["name"],
            "short": _short(class_item["name"], class_item["id"], 40),
        })

    groups_node = ElementTree.SubElement(
        root,
        "groups",
        {
            "options": "",
            "columns": "id,classid,name,entireclass,divisiontag",
        },
    )
    group_ids_by_group = {}
    group_rows = []
    for group_id, item in sorted(
        groups.items(), key=lambda row: row[1]["group"].name.casefold()
    ):
        asc_group_ids = []
        for candidate in item["class_candidates"]:
            class_id = classes_by_key[candidate["key"]]["id"]
            class_digest = sha1(
                candidate["key"].encode("utf-8")
            ).hexdigest()[:10]
            asc_group_id = f"{group_id}_{class_digest}"
            asc_group_ids.append(asc_group_id)
            group_rows.append((
                candidate["name"].casefold(),
                candidate["group_name"].casefold(),
                {
                    "id": asc_group_id,
                    "classid": class_id,
                    "name": candidate["group_name"],
                    "entireclass": (
                        "1" if candidate["entire_class"] else "0"
                    ),
                    "divisiontag": (
                        "" if candidate["entire_class"]
                        else (
                            "altair_division_"
                            f"{candidate['source_plan_line_id']}"
                        )
                    ),
                },
            ))
        group_ids_by_group[group_id] = asc_group_ids

    for _, _, attributes in sorted(
        group_rows,
        key=lambda item: (item[0], item[1], item[2]["id"]),
    ):
        ElementTree.SubElement(groups_node, "group", attributes)

    lessons_node = ElementTree.SubElement(
        root,
        "lessons",
        {
            "options": "",
            # Use aSc's native lesson table here. In particular, the native
            # importer reads the concrete available rooms from
            # ``classroomids``; the lesson-grid/group-subject import accepted
            # the workload but silently discarded that relation in aSc 2024.
            "columns": (
                "id,subjectid,classids,groupids,teacherids,classroomids,"
                "periodspercard,periodsperweek,divisiontag"
            ),
        },
    )
    for (group_id, subject_id, teacher_id), hours in sorted(
        lesson_hours.items()
    ):
        group_item = groups[group_id]
        class_ids = [
            classes_by_key[candidate["key"]]["id"]
            for candidate in group_item["class_candidates"]
        ]
        entire_class = all(
            candidate["entire_class"]
            for candidate in group_item["class_candidates"]
        )
        lesson_key = "|".join((group_id, subject_id, teacher_id))
        ElementTree.SubElement(lessons_node, "lesson", {
            "id": (
                "altair_lesson_"
                f"{sha1(lesson_key.encode('utf-8')).hexdigest()[:16]}"
            ),
            "classids": ",".join(class_ids),
            # Whole classes are already identified by classids. Supplying
            # artificial "entire class" group ids as well makes aSc reject
            # joined lessons such as a senior metagroup across two curricula.
            "groupids": (
                "" if entire_class
                else ",".join(group_ids_by_group[group_id])
            ),
            "subjectid": subject_id,
            "teacherids": teacher_id,
            "classroomids": classroom_id_by_teacher_id.get(
                teacher_id,
                "",
            ),
            "periodspercard": "1",
            "periodsperweek": _decimal_text(hours),
            "divisiontag": (
                "" if entire_class
                else (
                    "altair_division_"
                    f"{group_item['group'].source_plan_line_id}"
                )
            ),
        })

    ElementTree.indent(root, space="  ")
    return ElementTree.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )


__all__ = ["build_asc_timetable_xml"]
