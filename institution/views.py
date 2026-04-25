from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import SchoolIdentityForm
from .models import SchoolIdentity


def _safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return None


@login_required
def setup(request):
    identity = SchoolIdentity.objects.first()
    form = SchoolIdentityForm(request.POST or None, instance=identity)

    if request.method == "POST" and form.is_valid():
        identity = form.save()
        messages.success(request, "Identitas madrasah berhasil disimpan.")
        next_url = _safe_next_url(request) or ""
        if not next_url:
            next_url = request.session.pop("identity_setup_next", "")
        if not next_url:
            next_url = "/"
        return redirect(next_url)

    if not identity and request.GET.get("next"):
        request.session["identity_setup_next"] = request.GET.get("next", "")

    context = {
        "form": form,
        "page_kicker": "Identitas Madrasah",
        "page_title": "Lengkapi identitas madrasah",
        "page_description": "Data ini akan dipakai untuk kop surat, arsip, dan informasi dasar di seluruh aplikasi.",
        "submit_label": "Simpan identitas",
        "cancel_url": "dashboard:home" if identity and identity.is_complete else "logout",
        "identity": identity,
    }
    return render(request, "institution/setup.html", context)
