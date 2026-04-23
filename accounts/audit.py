from .models import ActivityLog


def record_activity(request, *, action, module, object_label="", object_id="", message=""):
    if request is None:
        return None

    return ActivityLog.objects.create(
        actor=getattr(request, "user", None) if getattr(request, "user", None) and request.user.is_authenticated else None,
        action=action,
        module=module,
        object_label=object_label,
        object_id=str(object_id) if object_id is not None else "",
        message=message,
        path=getattr(request, "path", "") or "",
    )
