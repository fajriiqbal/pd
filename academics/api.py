import json
from functools import wraps

from django.db import IntegrityError
from django.forms.models import model_to_dict
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from .forms import SubjectForm
from .models import Subject


def _api_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "Autentikasi diperlukan."}, status=401)
        return view_func(request, *args, **kwargs)

    return wrapper


def _subject_payload(subject):
    return {
        "id": subject.pk,
        "curriculum": subject.curriculum,
        "curriculum_label": subject.get_curriculum_display(),
        "name": subject.name,
        "code": subject.code,
        "category": subject.category,
        "category_label": subject.get_category_display(),
        "description": subject.description,
        "sort_order": subject.sort_order,
        "is_active": subject.is_active,
        "created_at": subject.created_at.isoformat() if subject.created_at else None,
        "updated_at": subject.updated_at.isoformat() if subject.updated_at else None,
    }


def _read_json_body(request):
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _form_errors(form):
    return {
        field: [str(error) for error in errors]
        for field, errors in form.errors.items()
    }


def _subject_form_data(payload, subject=None):
    data = model_to_dict(subject or Subject(), fields=SubjectForm.Meta.fields)
    data.update(payload)
    return data


@require_http_methods(["GET", "POST"])
@_api_login_required
def subject_collection(request):
    if request.method == "GET":
        subjects = Subject.objects.all().order_by("sort_order", "name")
        query = request.GET.get("q", "").strip()
        curriculum = request.GET.get("curriculum", "").strip()
        category = request.GET.get("category", "").strip()
        is_active = request.GET.get("is_active", "").strip().lower()

        if query:
            subjects = subjects.filter(name__icontains=query) | subjects.filter(code__icontains=query)
        if category:
            subjects = subjects.filter(category=category)
        if curriculum:
            subjects = subjects.filter(curriculum=curriculum)
        if is_active in {"true", "1", "yes"}:
            subjects = subjects.filter(is_active=True)
        elif is_active in {"false", "0", "no"}:
            subjects = subjects.filter(is_active=False)

        return JsonResponse(
            {
                "count": subjects.count(),
                "results": [_subject_payload(subject) for subject in subjects],
            }
        )

    payload = _read_json_body(request)
    if payload is None:
        return JsonResponse({"detail": "Body harus berupa JSON object yang valid."}, status=400)

    form = SubjectForm(_subject_form_data(payload))
    if not form.is_valid():
        return JsonResponse({"errors": _form_errors(form)}, status=400)

    try:
        subject = form.save()
    except IntegrityError:
        return JsonResponse({"detail": "Nama atau kode mata pelajaran sudah digunakan."}, status=409)

    return JsonResponse(_subject_payload(subject), status=201)


@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@_api_login_required
def subject_detail(request, pk):
    try:
        subject = Subject.objects.get(pk=pk)
    except Subject.DoesNotExist:
        return JsonResponse({"detail": "Mata pelajaran tidak ditemukan."}, status=404)

    if request.method == "GET":
        return JsonResponse(_subject_payload(subject))

    if request.method == "DELETE":
        if subject.class_subjects.exists():
            return JsonResponse(
                {"detail": "Mata pelajaran tidak bisa dihapus karena sudah dipakai pada kelas."},
                status=409,
            )
        subject.delete()
        return HttpResponse(status=204)

    payload = _read_json_body(request)
    if payload is None:
        return JsonResponse({"detail": "Body harus berupa JSON object yang valid."}, status=400)

    form = SubjectForm(_subject_form_data(payload, subject), instance=subject)
    if not form.is_valid():
        return JsonResponse({"errors": _form_errors(form)}, status=400)

    try:
        subject = form.save()
    except IntegrityError:
        return JsonResponse({"detail": "Nama atau kode mata pelajaran sudah digunakan."}, status=409)

    return JsonResponse(_subject_payload(subject))


@require_http_methods(["GET"])
@_api_login_required
def subject_categories(request):
    return JsonResponse(
        {
            "results": [
                {"value": value, "label": label}
                for value, label in Subject.Category.choices
            ],
            "curriculums": [
                {"value": value, "label": label}
                for value, label in Subject.Curriculum.choices
            ],
        }
    )
