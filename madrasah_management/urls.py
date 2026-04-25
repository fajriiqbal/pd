from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.views import SchoolLoginView

admin.site.site_header = "Admin PDM"
admin.site.site_title = "PDM"
admin.site.index_title = "Kelola Data Madsuka"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/login/", SchoolLoginView.as_view(), name="login"),
    path("auth/", include("django.contrib.auth.urls")),
    path("institution/", include("institution.urls")),
    path("api/", include("academics.api_urls")),
    path("", include("dashboard.urls")),
    path("academics/", include("academics.urls")),
    path("accounts/", include("accounts.urls")),
    path("students/", include("students.urls")),
    path("teachers/", include("teachers.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
