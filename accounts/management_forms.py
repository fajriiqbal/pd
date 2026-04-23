from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import CustomUser

BASE_INPUT_CLASS = (
    "mt-1 w-full rounded-xl border border-slate-200 bg-white/95 px-3.5 py-2.5 "
    "text-sm text-slate-900 shadow-sm transition focus:border-slate-400 focus:outline-none focus:ring-0"
)


class AccountRecordForm(forms.ModelForm):
    password = forms.CharField(
        label="Password login",
        required=False,
        widget=forms.PasswordInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Isi password akun"}),
        help_text="Wajib diisi saat membuat akun baru. Kosongkan saat edit bila tidak ingin mengubah password.",
    )
    confirm_password = forms.CharField(
        label="Konfirmasi password",
        required=False,
        widget=forms.PasswordInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Ulangi password akun"}),
    )

    class Meta:
        model = CustomUser
        fields = [
            "full_name",
            "username",
            "email",
            "phone_number",
            "role",
            "is_school_active",
            "is_active",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Nama lengkap pengguna"}),
            "username": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Username login"}),
            "email": forms.EmailInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "opsional@email.com"}),
            "phone_number": forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "08xxxxxxxxxx"}),
            "role": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "is_school_active": forms.CheckboxInput(attrs={"class": "mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900"}),
            "is_active": forms.CheckboxInput(attrs={"class": "mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-900"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["is_school_active"].initial = self.instance.is_school_active
            self.fields["is_active"].initial = self.instance.is_active

            if hasattr(self.instance, "student_profile"):
                self.fields["role"].disabled = True
                self.fields["role"].help_text = "Role dikunci karena akun ini terhubung ke data siswa."
            elif hasattr(self.instance, "teacher_profile"):
                self.fields["role"].disabled = True
                self.fields["role"].help_text = "Role dikunci karena akun ini terhubung ke data guru."
        else:
            self.fields["is_school_active"].initial = True
            self.fields["is_active"].initial = True
            self.fields["role"].initial = CustomUser.Role.ADMIN

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        qs = CustomUser.objects.filter(username=username)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Username ini sudah digunakan.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if not self.instance.pk and not password:
            self.add_error("password", "Password wajib diisi untuk akun baru.")

        if password or confirm_password:
            if password != confirm_password:
                self.add_error("confirm_password", "Konfirmasi password tidak cocok.")

        if self.instance.pk:
            if hasattr(self.instance, "student_profile"):
                cleaned_data["role"] = CustomUser.Role.STUDENT
            elif hasattr(self.instance, "teacher_profile"):
                cleaned_data["role"] = CustomUser.Role.TEACHER

        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        if user.role == CustomUser.Role.ADMIN:
            user.is_staff = True
        elif not user.is_superuser:
            user.is_staff = False

        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)

        if commit:
            user.save()
        return user


class AccountPasswordForm(forms.Form):
    password = forms.CharField(
        label="Password baru",
        widget=forms.PasswordInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Masukkan password baru"}),
    )
    confirm_password = forms.CharField(
        label="Konfirmasi password baru",
        widget=forms.PasswordInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "Ulangi password baru"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Konfirmasi password tidak cocok.")
        return cleaned_data
