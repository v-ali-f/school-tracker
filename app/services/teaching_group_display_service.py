import re


_CLASS_TOKEN_RE = re.compile(
    r"(?<![\w])(?:1[01]|[1-9])\s*[А-ЯЁA-Z](?![\w])",
    re.IGNORECASE,
)
_SUBGROUP_NUMBER_RE = re.compile(
    r"групп(?:а|ы)?\s*№?\s*(\d+)",
    re.IGNORECASE,
)


def _class_sort_key(value):
    match = re.match(r"^\s*(\d+)", value or "")
    return (
        int(match.group(1)) if match else 99,
        (value or "").casefold(),
    )


def teaching_group_source_groups(group):
    if group is None:
        return []
    if group.group_type == "METAGROUP":
        return [
            link.source_group
            for link in (getattr(group, "metagroup_sources", None) or [])
            if link.source_group is not None
        ]
    return [group]


def teaching_group_class_names(group):
    names = {
        link.population_snapshot_class.name_snapshot
        for source_group in teaching_group_source_groups(group)
        for link in (
            getattr(source_group, "source_classes", None) or []
        )
        if link.population_snapshot_class is not None
        and link.population_snapshot_class.name_snapshot
    }
    if not names and group is not None:
        names.update(
            token.replace(" ", "").upper()
            for token in _CLASS_TOKEN_RE.findall(group.name or "")
        )
    return sorted(names, key=_class_sort_key)


def teaching_group_class_label(group):
    return ", ".join(teaching_group_class_names(group)) or "—"


def teaching_group_assignment_label(group):
    if group is None:
        return "Без учебной группы"
    if group.group_type == "CLASS":
        return "Весь класс"
    if group.group_type == "SUBGROUP":
        match = _SUBGROUP_NUMBER_RE.search(group.name or "")
        return f"Группа {match.group(1)}" if match else group.name
    if group.group_type == "METAGROUP":
        class_names = teaching_group_class_names(group)
        return (
            f"Метагруппа: {' + '.join(class_names)}"
            if class_names else group.name or "Метагруппа"
        )
    if group.group_type in {
        "EXTRACURRICULAR_GROUP",
        "ADDITIONAL_GROUP",
    }:
        match = _SUBGROUP_NUMBER_RE.search(group.name or "")
        if match:
            return f"Группа {match.group(1)}"
        source_links = getattr(group, "source_classes", None) or []
        if (
            len(source_links) == 1
            and getattr(source_links[0], "relation_kind", None) == "FULL"
        ):
            return "Весь класс"
        class_names = teaching_group_class_names(group)
        return (
            f"Группа: {' + '.join(class_names)}"
            if len(class_names) > 1 else "Группа"
        )
    if group.group_type == "INDIVIDUAL":
        return "Индивидуально"
    return group.name or "Учебная группа"
