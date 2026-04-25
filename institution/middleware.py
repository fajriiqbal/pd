from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import reverse

from .models import SchoolIdentity


class SchoolIdentitySetupMiddleware:
    allowed_prefixes = (
        "/admin/",
        "/auth/",
        "/institution/setup/",
        "/api/",
        "/dashboard/health/",
        "/static/",
        "/media/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.school_identity = SchoolIdentity.objects.first()

        if request.user.is_authenticated and not self._is_allowed_path(request.path_info):
            identity = request.school_identity
            if not identity or not identity.is_complete:
                setup_url = reverse("institution:setup")
                query_string = urlencode({"next": request.get_full_path()})
                return redirect(f"{setup_url}?{query_string}")

        response = self.get_response(request)
        return response

    def _is_allowed_path(self, path):
        return any(path.startswith(prefix) for prefix in self.allowed_prefixes)
