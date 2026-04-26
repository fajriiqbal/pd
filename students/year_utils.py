import re


def infer_level_order_from_label(class_label: str | None) -> int | None:
    match = re.search(r"(\d{1,2})", (class_label or "").strip())
    if match:
        return int(match.group(1))
    return None


def infer_entry_year_from_level(level_order: int | None, fallback_year: int | None = None) -> int | None:
    if level_order in {7, 8, 9}:
        return 2025 - (level_order - 7)
    return fallback_year


def infer_student_entry_year(student, fallback_year: int | None = None) -> int | None:
    if getattr(student, "study_group_id", None) and getattr(student, "study_group", None):
        school_class = getattr(student.study_group, "school_class", None)
        if school_class:
            inferred = infer_entry_year_from_level(school_class.level_order, fallback_year)
            if inferred:
                return inferred

    class_label = getattr(student, "class_name", "")
    level_order = infer_level_order_from_label(class_label)
    inferred = infer_entry_year_from_level(level_order, fallback_year)
    if inferred:
        return inferred

    return getattr(student, "entry_year", None) or fallback_year
