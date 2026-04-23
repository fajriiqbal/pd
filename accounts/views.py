from django.contrib import messages
from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import MadrasahAuthenticationForm
from .management_forms import AccountPasswordForm, AccountRecordForm
from .models import CustomUser


class SchoolLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = MadrasahAuthenticationForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.request.user
        messages.success(self.request, f"Selamat datang, {user.full_name or user.username}.")
        self.request.session["show_login_briefing"] = True
        return response


@login_required
def user_list(request):
    query = request.GET.get("q", "").strip()
    users = CustomUser.objects.all().order_by("full_name", "username")

    if query:
        users = users.filter(
            Q(full_name__icontains=query)
            | Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(phone_number__icontains=query)
        )

    context = {"users": users, "query": query}
    return render(request, "accounts/user_list.html", context)


@login_required
def user_create(request):
    form = AccountRecordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Akun pengguna berhasil ditambahkan.")
        return redirect("accounts:list")

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Manajemen Akun",
            "page_title": "Tambah akun pengguna",
            "page_description": "Gunakan menu ini untuk menambah akun operator atau akun umum lain yang belum terhubung ke data siswa/guru.",
            "submit_label": "Simpan akun",
            "cancel_url": "accounts:list",
            "checkbox_fields": ["is_school_active", "is_active"],
        },
    )


@login_required
def user_update(request, pk):
    account = get_object_or_404(CustomUser, pk=pk)
    form = AccountRecordForm(request.POST or None, instance=account)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Akun pengguna berhasil diperbarui.")
        return redirect("accounts:list")

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Manajemen Akun",
            "page_title": f"Edit akun {account.full_name}",
            "page_description": "Perbarui informasi akun, role, dan status aktif pengguna ini.",
            "submit_label": "Update akun",
            "cancel_url": "accounts:list",
            "checkbox_fields": ["is_school_active", "is_active"],
        },
    )


@login_required
def user_password_update(request, pk):
    account = get_object_or_404(CustomUser, pk=pk)
    form = AccountPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        account.set_password(form.cleaned_data["password"])
        account.save(update_fields=["password"])
        messages.success(request, "Password akun berhasil diperbarui.")
        return redirect("accounts:list")

    return render(
        request,
        "shared/form_page.html",
        {
            "form": form,
            "page_kicker": "Manajemen Akun",
            "page_title": f"Ubah password {account.full_name}",
            "page_description": "Masukkan password baru untuk akun ini. Gunakan bila operator perlu reset akses login.",
            "submit_label": "Simpan password baru",
            "cancel_url": "accounts:list",
            "checkbox_fields": [],
        },
    )


@login_required
def user_delete(request, pk):
    account = get_object_or_404(CustomUser, pk=pk)

    if request.user.pk == account.pk:
        messages.error(request, "Anda tidak bisa menghapus akun yang sedang dipakai untuk login.")
        return redirect("accounts:list")

    if hasattr(account, "student_profile"):
        messages.error(request, "Akun ini terhubung ke data siswa. Hapus lewat modul siswa agar konsisten.")
        return redirect("accounts:list")

    if hasattr(account, "teacher_profile"):
        messages.error(request, "Akun ini terhubung ke data guru. Hapus lewat modul guru agar konsisten.")
        return redirect("accounts:list")

    if request.method == "POST":
        account.delete()
        messages.success(request, "Akun pengguna berhasil dihapus.")
        return redirect("accounts:list")

    return render(
        request,
        "shared/confirm_delete.html",
        {
            "item_name": account.full_name,
            "item_type": "akun pengguna",
            "cancel_url": "accounts:list",
        },
    )
